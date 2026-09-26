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

/// Routes by path/bearer-token so a single transport can stand in for a
/// whole DEBUG dev-token bootstrap sequence (net-auth spec §4): `GET
/// /auth/dev-token` (no auth header) followed by `GET /auth/me` bearing the
/// token that call just returned.
private actor RoutingStubTransport: HTTPTransport {
    private let devTokenBody: Data
    private let meBody: Data
    private let meStatusCode: Int
    private(set) var receivedAuthHeaders: [String?] = []

    init(devTokenBody: Data, meBody: Data, meStatusCode: Int = 200) {
        self.devTokenBody = devTokenBody
        self.meBody = meBody
        self.meStatusCode = meStatusCode
    }

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        receivedAuthHeaders.append(request.value(forHTTPHeaderField: "Authorization"))
        let path = request.url?.path ?? ""
        if path.hasSuffix("/auth/dev-token") {
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (devTokenBody, response)
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: meStatusCode, httpVersion: nil, headerFields: nil)!
        return (meBody, response)
    }
}

private struct StubTokenProvider: TokenProviding {
    let token: String?
    func currentToken() async -> String? { token }
}

/// A `TokenProviding` a test can update mid-sequence — stands in for
/// `AuthService.bearerToken` switching from "no token" to "the dev token
/// that was just issued" between the two calls of the bootstrap sequence.
private actor MutableTokenBox: TokenProviding {
    private var token: String?
    func currentToken() async -> String? { token }
    func setToken(_ newValue: String?) { token = newValue }
}

private actor RecoveringTransport: HTTPTransport {
    private(set) var headers: [String?] = []

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        let header = request.value(forHTTPHeaderField: "Authorization")
        headers.append(header)
        let status = header == "Bearer renewed" ? 200 : 401
        let body = #"{"id":"u1","email":"a@example.com","is_active":true}"#.data(using: .utf8)!
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        return (body, response)
    }
}

private actor SessionStore: AuthSessionStore {
    private var session: AuthSession?
    init(_ session: AuthSession) { self.session = session }
    func load() -> AuthSession? { session }
    func save(_ session: AuthSession) { self.session = session }
    func clear() { session = nil }
}

private actor PendingStore: PendingAuthorizationStore {
    func load() -> PendingAuthorization? { nil }
    func save(_ authorization: PendingAuthorization) {}
    func clear() {}
}

private struct RotatingIdentityClient: MagicLinkAuthenticationClient {
    func requestMagicLink(email: String, codeChallenge: String) async throws -> MagicLinkRequestResult {
        MagicLinkRequestResult(accepted: true)
    }
    func exchangeAuthorizationCode(code: String, codeVerifier: String) async throws -> AuthSession {
        AuthSession(bearerToken: "renewed", refreshToken: "refresh-2")
    }
    func refreshSession(refreshToken: String) async throws -> AuthSession {
        AuthSession(bearerToken: "renewed", refreshToken: "refresh-2")
    }
    func fetchIdentity(bearerToken: String) async throws -> HouseholdIdentity {
        HouseholdIdentity(email: "a@example.com")
    }
}

@Suite("CodeMonetRESTClient")
struct CodeMonetRESTClientTests {
    @Test("a real Platform controller rotates and persists the token used by the replay")
    @MainActor
    func platformRecoveryComposesWithRESTClient() async throws {
        let cached = AuthSession(
            bearerToken: "expired",
            refreshToken: "refresh-1",
            expiresAt: Date().addingTimeInterval(600)
        )
        let store = SessionStore(cached)
        let controller = AuthenticationController(
            client: RotatingIdentityClient(),
            sessionStore: store,
            pendingAuthorizationStore: PendingStore()
        )
        await controller.restoreSession()
        let transport = RecoveringTransport()
        let tokenBox = MutableTokenBox()
        await tokenBox.setToken("expired")
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: tokenBox,
            transport: transport,
            onUnauthorized: { rejected in
                await controller.handleUnauthorizedRequest(bearerToken: rejected)
                return await controller.session?.bearerToken
            }
        )

        let user = try await client.currentUser()

        #expect(user.id == "u1")
        #expect(await store.load()?.refreshToken == "refresh-2")
        #expect(await transport.headers == ["Bearer expired", "Bearer renewed"])
    }

    @Test("a rejected read refreshes through Platform and replays once with the replacement")
    func rejectedReadUsesReplacementToken() async throws {
        let transport = RecoveringTransport()
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: StubTokenProvider(token: "expired"),
            transport: transport,
            onUnauthorized: { rejected in
                #expect(rejected == "expired")
                return "renewed"
            }
        )

        let user = try await client.currentUser()

        #expect(user.id == "u1")
        #expect(await transport.headers == ["Bearer expired", "Bearer renewed"])
    }

    @Test("without a replacement, a rejected read keeps its original failure")
    func rejectedReadWithoutReplacementDoesNotReplay() async {
        let transport = RecoveringTransport()
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: StubTokenProvider(token: "expired"),
            transport: transport,
            onUnauthorized: { _ in "expired" }
        )

        do {
            _ = try await client.currentUser()
            Issue.record("expected unauthorized response")
        } catch MobileAPIError.unauthorized {
            #expect(await transport.headers == ["Bearer expired"])
        } catch {
            Issue.record("unexpected error: \(error)")
        }
    }

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

    /// Net-auth spec §4's full DEBUG bootstrap sequence — `GET
    /// /auth/dev-token` (no auth header), then `GET /auth/me` bearing the
    /// token that call just returned — is exactly what `AuthService
    /// .tryDevTokenBootstrap()` does; that method itself lives in the
    /// `CodeMonet` app target and can only be exercised via `xcodebuild`
    /// (no simulator is available in this environment/worktree — see
    /// net-auth spec §4's acceptance note). This test covers the same
    /// two-call sequence and header transition at the REST-client level with
    /// a stubbed transport, standing in for a live `localhost:8000` check.
    @Test("DEBUG dev-token bootstrap: devToken() then currentUser() authenticate with zero taps")
    func devTokenBootstrapSequenceSignsIn() async throws {
        let devTokenJSON = #"{"access_token":"dev-abc","user_id":"dev-1"}"#.data(using: .utf8)!
        let meJSON = #"{"id":"dev-1","email":"dev@local.test","is_active":true}"#.data(using: .utf8)!
        let transport = RoutingStubTransport(devTokenBody: devTokenJSON, meBody: meJSON)
        let tokenBox = MutableTokenBox()
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: tokenBox,
            transport: transport
        )

        let devToken = try await client.devToken()
        #expect(devToken.accessToken == "dev-abc")
        await tokenBox.setToken(devToken.accessToken)
        let user = try await client.currentUser()
        #expect(user.id == "dev-1")
        #expect(user.isActive)

        let headers = await transport.receivedAuthHeaders
        #expect(headers.count == 2)
        #expect(headers[0] == nil) // /auth/dev-token: no Authorization header at all
        #expect(headers[1] == "Bearer dev-abc") // /auth/me: bearer = the just-issued dev token
    }

    @Test("a 403 dev-token response (dev_mode disabled server-side) surfaces as .unauthorized, never a crash")
    func devTokenDisabledMapsToUnauthorized() async throws {
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: StubTokenProvider(token: nil),
            transport: StubTransport(statusCode: 403, body: Data())
        )
        do {
            _ = try await client.devToken()
            Issue.record("expected devToken() to throw")
        } catch let error as MobileAPIError {
            #expect(error == .unauthorized)
        }
    }

    @Test("an identity-mapping failure (net-auth spec §0.2) surfaces /auth/me's 401 as .unauthorized")
    func currentUserUnmappedIdentityMapsToUnauthorized() async throws {
        let client = CodeMonetRESTClient(
            baseURL: URL(string: "http://localhost:8000")!,
            tokenProvider: StubTokenProvider(token: "tok"),
            transport: StubTransport(statusCode: 401, body: Data())
        )
        do {
            _ = try await client.currentUser()
            Issue.record("expected currentUser() to throw")
        } catch let error as MobileAPIError {
            #expect(error == .unauthorized)
        }
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
