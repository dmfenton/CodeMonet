import FentonMobileCore
import Foundation
import MonetProtocol

/// Fetches program-painting version assets — `final.png`, `painting.py`,
/// and the (possibly still growing) `performance.bin` stream — directly from
/// their resolved, capability-token URLs (`MonetRender.PaintingAssetURL`). Deliberately **not** routed through
/// `CodeMonetRESTClient`/`MobileAPIClient`: those always attach a bearer
/// token and resolve a path relative to `baseURL`, but painting-asset URLs
/// carry their own unguessable per-version token and are meant to load
/// "like share links" (server's `routes/paintings.py` doc comment) — no
/// auth header, and already fully resolved (absolute) strings by the time
/// they reach here.
public struct PaintingAssetClient: Sendable {
    private let transport: any HTTPTransport
    /// Session configuration for `byteStream(at:)` (a delegate session per
    /// stream). Injectable so tests can stub the network with a
    /// `URLProtocol`.
    private let streamConfiguration: @Sendable () -> URLSessionConfiguration

    /// A live performance response can sit idle while the program computes
    /// without painting; the server follows it for at most the paint
    /// timeout + 30 s (`routes/paintings.py` `_LIVE_MAX_S`, 270 s), so the
    /// stream must not give up at URLSession's 60 s idle default.
    public static let streamIdleTimeout: TimeInterval = 300

    public static func defaultStreamConfiguration() -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = streamIdleTimeout
        return configuration
    }

    public init(
        transport: any HTTPTransport = URLSession.shared,
        streamConfiguration: @escaping @Sendable () -> URLSessionConfiguration = { PaintingAssetClient.defaultStreamConfiguration() }
    ) {
        self.transport = transport
        self.streamConfiguration = streamConfiguration
    }

    public enum FetchError: Error, Equatable, Sendable {
        case invalidURL(String)
        case http(statusCode: Int)
        case decoding(String)
    }

    /// Fetches raw image bytes (`final.png`).
    /// Decoding to a drawable image is the caller's job (`MonetRender`
    /// owns `CGImage`, not this package).
    public func imageData(at urlString: String) async throws -> Data {
        try await data(at: urlString)
    }

    /// Fetches a version's `painting.py` (the program that rendered it) as
    /// UTF-8 text.
    public func text(at urlString: String) async throws -> String {
        let raw = try await data(at: urlString)
        guard let text = String(data: raw, encoding: .utf8) else {
            throw FetchError.decoding("not UTF-8 text")
        }
        return text
    }

    /// Streams an asset's bytes as they arrive from the network — for
    /// `performance.bin`, which the server keeps open and extends while the
    /// paint run writes it (until its end/error frame). A non-2xx status
    /// finishes the stream with `FetchError.http`; cancelling the consuming
    /// task cancels the request.
    public func byteStream(at urlString: String) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { continuation in
            guard let url = URL(string: urlString) else {
                continuation.finish(throwing: FetchError.invalidURL(urlString))
                return
            }
            let delegate = ByteStreamDelegate(continuation: continuation)
            let session = URLSession(configuration: streamConfiguration(), delegate: delegate, delegateQueue: nil)
            let task = session.dataTask(with: URLRequest(url: url))
            continuation.onTermination = { _ in
                task.cancel()
                session.invalidateAndCancel()
            }
            task.resume()
        }
    }

    private func data(at urlString: String) async throws -> Data {
        guard let url = URL(string: urlString) else {
            throw FetchError.invalidURL(urlString)
        }
        let (data, response) = try await transport.data(for: URLRequest(url: url))
        if let http = response as? HTTPURLResponse, !(200 ..< 300).contains(http.statusCode) {
            throw FetchError.http(statusCode: http.statusCode)
        }
        return data
    }
}

/// Forwards a data task's bytes into an `AsyncThrowingStream` as each network
/// chunk arrives. The session holds the delegate until it is invalidated
/// (on completion or cancellation).
private final class ByteStreamDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let continuation: AsyncThrowingStream<Data, Error>.Continuation

    init(continuation: AsyncThrowingStream<Data, Error>.Continuation) {
        self.continuation = continuation
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        if let http = response as? HTTPURLResponse, !(200 ..< 300).contains(http.statusCode) {
            continuation.finish(throwing: PaintingAssetClient.FetchError.http(statusCode: http.statusCode))
            completionHandler(.cancel)
            return
        }
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        continuation.yield(data)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error {
            continuation.finish(throwing: error)
        } else {
            continuation.finish()
        }
        session.finishTasksAndInvalidate()
    }
}
