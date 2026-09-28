import FentonMobileCore
import Foundation
@testable import MonetNetworking
import Testing

private struct TextStubTransport: HTTPTransport {
    let statusCode: Int
    let body: Data
    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        let url = try #require(request.url)
        let response = try #require(HTTPURLResponse(url: url, statusCode: statusCode, httpVersion: nil, headerFields: nil))
        #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
        return (body, response)
    }
}

@Suite("PaintingAssetClient text")
struct PaintingAssetClientTests {
    @Test("fetches painting.py as UTF-8 text without auth")
    func fetchesProgramText() async throws {
        let client = PaintingAssetClient(transport: TextStubTransport(statusCode: 200, body: Data("cv.stage(\"sky\")\n".utf8)))
        let text = try await client.text(at: "http://localhost/painting-assets/u/t/painting.py")
        #expect(text == "cv.stage(\"sky\")\n")
    }

    @Test("a 404 (older server without painting.py) throws an http error")
    func missingProgramThrows() async {
        let client = PaintingAssetClient(transport: TextStubTransport(statusCode: 404, body: Data()))
        await #expect(throws: PaintingAssetClient.FetchError.http(statusCode: 404)) {
            _ = try await client.text(at: "http://localhost/painting-assets/u/t/painting.py")
        }
    }
}

/// Serves canned responses by URL path, delivering the body in separate
/// chunks (like a stream the server is still writing).
private final class ChunkedStubProtocol: URLProtocol {
    struct Response {
        var statusCode: Int
        var chunks: [Data]
    }

    nonisolated(unsafe) static var responses: [String: Response] = [:]
    private static let lock = NSLock()

    static func register(_ path: String, _ response: Response) {
        lock.withLock { responses[path] = response }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url, let stub = Self.lock.withLock({ Self.responses[url.path] }),
              let response = HTTPURLResponse(url: url, statusCode: stub.statusCode, httpVersion: nil, headerFields: nil)
        else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        for chunk in stub.chunks { client?.urlProtocol(self, didLoad: chunk) }
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@Suite("PaintingAssetClient byte stream")
struct PaintingAssetClientStreamTests {
    private let client = PaintingAssetClient(streamConfiguration: {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ChunkedStubProtocol.self]
        return configuration
    })

    @Test("streams a growing asset's bytes as they arrive")
    func streamsChunks() async throws {
        ChunkedStubProtocol.register("/painting-assets/u/live/performance.bin", .init(statusCode: 200, chunks: [
            Data([1, 2, 3]), Data([4, 5]),
        ]))
        var received = Data()
        for try await chunk in client.byteStream(at: "http://localhost/painting-assets/u/live/performance.bin") {
            received.append(chunk)
        }
        #expect(received == Data([1, 2, 3, 4, 5]))
    }

    @Test("a missing stream (a version from before performances) fails with its status")
    func missingStreamThrows() async {
        ChunkedStubProtocol.register("/painting-assets/u/old/performance.bin", .init(statusCode: 404, chunks: [Data("nope".utf8)]))
        await #expect(throws: PaintingAssetClient.FetchError.http(statusCode: 404)) {
            for try await _ in client.byteStream(at: "http://localhost/painting-assets/u/old/performance.bin") {}
        }
    }
}
