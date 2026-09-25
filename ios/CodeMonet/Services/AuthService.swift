import FentonMobileCore
import Foundation
import MonetNetworking
import Observation

/// App-facing auth state (net-auth spec §3.4). Richer than a single
/// `loading` boolean so the UI can distinguish "restoring a cached session"
/// from "actively exchanging a magic-link code" (ux spec §10's suggested
/// native improvement).
public enum AppAuthState: Equatable, Sendable {
    case restoring
    case signedOut
    case signingIn
    case exchangingCode
    case signedIn(UserResponse)
    case error(String)
}

/// Wraps `FentonMobileCore.AuthenticationController` with the two required
/// CodeMonet-specific deviations (net-auth spec §0.1-0.2, §3.4, §4):
/// 1. after a successful code exchange, independently verifies the platform
///    identity maps to a real CodeMonet user via `GET /auth/me`, signing back
///    out on failure rather than trusting `.signedIn` alone;
/// 2. a DEBUG-only in-memory dev-token session, tried once when no usable
///    cached/refreshable session exists, so the simulator can be driven
///    against `localhost` with zero taps.
@MainActor
@Observable
public final class AuthService {
    public private(set) var state: AppAuthState = .restoring

    private let controller: AuthenticationController
    private let restClient: CodeMonetRESTClient
    private let tokenBox: TokenBox
    /// DEBUG-only, never persisted (net-auth spec §4) — never routed through
    /// `AuthenticationController`'s refresh machinery.
    private var debugToken: String?

    public init(environment: CodeMonetEnvironment) {
        let identityAPI = MobileAPIClient(baseURL: CodeMonetEnvironment.identityBaseURL)
        let codeMonetAPI = MobileAPIClient(baseURL: environment.apiBaseURL)
        let client = CodeMonetIdentityClient(identityAPI: identityAPI, codeMonetAPI: codeMonetAPI)
        let stores = KeychainAuthenticationStores(service: "net.dmfenton.sketchpad")
        controller = AuthenticationController(
            client: client,
            sessionStore: stores.session,
            pendingAuthorizationStore: stores.pendingAuthorization,
            refreshRotationStore: stores.refreshRotation
        )
        let box = TokenBox { nil }
        tokenBox = box
        restClient = CodeMonetRESTClient(baseURL: environment.apiBaseURL, tokenProvider: box)
        // Now that `self` is fully initialized, point the box at the real,
        // still-current token on every call (debug token, if any, else the
        // controller's platform session).
        box.replace { [weak self] in await self?.bearerToken }
    }

    public var bearerToken: String? {
        debugToken ?? controller.session?.bearerToken
    }

    /// Call once at launch. Restores any cached session, then — only if that
    /// leaves the app signed out — tries the DEBUG dev-token bootstrap
    /// (net-auth spec §4).
    public func start() async {
        state = .restoring
        await controller.restoreSession()
        await syncStateFromController()
        #if DEBUG
            if case .signedOut = state {
                await tryDevTokenBootstrap()
            } else if case .error = state {
                await tryDevTokenBootstrap()
            }
        #endif
    }

    public func requestMagicLink(email: String) async throws {
        state = .signingIn
        _ = try await controller.requestMagicLink(email: email)
        state = .signedOut // caller shows the "check your email" success box; not yet authenticated.
    }

    /// Consumes a deep-linked authorization code (net-auth spec §5.1),
    /// applying the identity-mapping check from §0.2/§3.4 before ever
    /// reporting `.signedIn`.
    public func consume(code: String) async throws {
        state = .exchangingCode
        try await controller.exchangeAuthorizationCode(code)
        await verifyIdentityMapping()
    }

    public func signOut() async {
        debugToken = nil
        await controller.signOut()
        state = .signedOut
    }

    private func syncStateFromController() async {
        switch controller.state {
        case .restoring:
            state = .restoring
        case .signedOut, .reauthenticationRequired:
            state = .signedOut
        case .requestingMagicLink:
            state = .signingIn
        case .exchangingAuthorizationCode:
            state = .exchangingCode
        case .signedIn:
            await verifyIdentityMapping()
        }
    }

    /// Net-auth spec §0.2: a successful token exchange alone does not prove
    /// the platform identity maps to a CodeMonet user.
    private func verifyIdentityMapping() async {
        do {
            let user = try await restClient.currentUser()
            state = .signedIn(user)
        } catch {
            await controller.signOut()
            state = .error("Identity could not be mapped to a CodeMonet user")
        }
    }

    #if DEBUG
        private func tryDevTokenBootstrap() async {
            do {
                let response = try await restClient.devToken()
                debugToken = response.accessToken
                let user = try await restClient.currentUser()
                state = .signedIn(user)
            } catch {
                // Development server is optional during static UI work —
                // never surface this failure (net-auth spec §4).
                debugToken = nil
                state = .signedOut
            }
        }
    #endif
}

/// A `TokenProviding` box so `CodeMonetRESTClient` can read `AuthService`'s
/// *current* token lazily (including a debug token set after construction)
/// without `AuthService` and `CodeMonetRESTClient` depending on each other's
/// concrete types.
private final class TokenBox: TokenProviding, @unchecked Sendable {
    private var provider: @Sendable () async -> String?
    init(_ provider: @escaping @Sendable () async -> String?) {
        self.provider = provider
    }

    func currentToken() async -> String? {
        await provider()
    }

    func replace(_ provider: @escaping @Sendable () async -> String?) {
        self.provider = provider
    }
}
