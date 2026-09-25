import FentonMobileCore
import Foundation
import Testing
@testable import MonetNetworking

private struct StubTransport: HTTPTransport {
    let statusCode: Int
    let body: Data
    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        let response = HTTPURLResponse(url: request.url!, statusCode: statusCode, httpVersion: nil, headerFields: nil)!
        return (body, response)
    }
}

private struct StubTokenProvider: TokenProviding {
    let token: String?
    func currentToken() async -> String? { token }
}

@Suite("CodeMonetRESTClient")
struct CodeMonetRESTClientTests {
    @Test("decodes /auth/me")
    func decodesCurrentUser() async throws {
        let json = #"{"id":"u1","email":"a@example.com","is_active":true}"#.data(using: .utf8)!
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: StubTokenProvider(token: "tok"),
            transport: StubTransport(statusCode: 200, body: json)
        )
        let user = try await client.currentUser()
        #expect(user.id == "u1")
        #expect(user.isActive)
    }

    @Test("decodes /auth/dev-token")
    func decodesDevToken() async throws {
        let json = #"{"access_token":"abc","user_id":"dev-1"}"#.data(using: .utf8)!
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: StubTokenProvider(token: nil),
            transport: StubTransport(statusCode: 200, body: json)
        )
        let response = try await client.devToken()
        #expect(response.accessToken == "abc")
    }
}

@Suite("CodeMonetEnvironment")
struct CodeMonetEnvironmentTests {
    @Test("production uses split api/ws hosts, ws not nested under /api")
    func productionHosts() {
        #expect(CodeMonetEnvironment.production.apiBaseURL.absoluteString == "https://monet.dmfenton.net/api")
        #expect(CodeMonetEnvironment.production.wsBaseURL.absoluteString == "wss://monet.dmfenton.net/ws")
    }
}
