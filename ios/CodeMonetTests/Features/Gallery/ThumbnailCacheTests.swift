@testable import CodeMonet
import FentonMobileCore
import Foundation
import MonetNetworking
import Testing

/// `ThumbnailCache` tests run against a fake `HTTPTransport` (no live
/// server) — a 1x1 transparent PNG fixture stands in for a real thumbnail.
@Suite("ThumbnailCache")
@MainActor
struct ThumbnailCacheTests {
    @Test("load caches a decoded image, keyed by token")
    func loadCachesDecodedImage() async {
        let token = "piece_\(UUID().uuidString)"
        let transport = CountingTransport(data: Fixtures.onePixelPNG, statusCode: 200)
        let rest = CodeMonetRESTClient(baseURL: Fixtures.baseURL, tokenProvider: FakeTokenProvider(), transport: transport)

        #expect(ThumbnailCache.shared.image(for: token) == nil)
        await ThumbnailCache.shared.load(token: token, using: rest)
        #expect(ThumbnailCache.shared.image(for: token) != nil)
        #expect(ThumbnailCache.shared.didFail(token) == false)
    }

    @Test("load is a no-op once cached — doesn't refetch")
    func loadDoesNotRefetchOnceCached() async {
        let token = "piece_\(UUID().uuidString)"
        let transport = CountingTransport(data: Fixtures.onePixelPNG, statusCode: 200)
        let rest = CodeMonetRESTClient(baseURL: Fixtures.baseURL, tokenProvider: FakeTokenProvider(), transport: transport)

        await ThumbnailCache.shared.load(token: token, using: rest)
        await ThumbnailCache.shared.load(token: token, using: rest)
        #expect(transport.requestCount == 1)
    }

    @Test("a failed fetch is remembered as failed, not cached as an image")
    func loadMarksFailureOnError() async {
        let token = "piece_\(UUID().uuidString)"
        let transport = CountingTransport(data: Data(), statusCode: 404)
        let rest = CodeMonetRESTClient(baseURL: Fixtures.baseURL, tokenProvider: FakeTokenProvider(), transport: transport)

        await ThumbnailCache.shared.load(token: token, using: rest)
        #expect(ThumbnailCache.shared.image(for: token) == nil)
        #expect(ThumbnailCache.shared.didFail(token))
    }
}

private enum Fixtures {
    static let baseURL: URL = {
        guard let url = URL(string: "https://example.test") else {
            preconditionFailure("invalid fixture URL literal")
        }
        return url
    }()

    /// A minimal valid 1x1 transparent PNG, so `UIImage(data:)` succeeds.
    static let onePixelPNG: Data = {
        let base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        guard let data = Data(base64Encoded: base64) else {
            preconditionFailure("invalid fixture base64 literal")
        }
        return data
    }()
}

private struct FakeTokenProvider: TokenProviding {
    func currentToken() async -> String? { "fake-token" }
}

private final class CountingTransport: HTTPTransport, @unchecked Sendable {
    let data: Data
    let statusCode: Int
    private(set) var requestCount = 0

    init(data: Data, statusCode: Int) {
        self.data = data
        self.statusCode = statusCode
    }

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        requestCount += 1
        guard let response = HTTPURLResponse(
            url: request.url ?? Fixtures.baseURL,
            statusCode: statusCode,
            httpVersion: nil,
            headerFields: nil
        ) else {
            preconditionFailure("failed to construct fake HTTPURLResponse")
        }
        return (data, response)
    }
}
