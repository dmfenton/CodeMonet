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
