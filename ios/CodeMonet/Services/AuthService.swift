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

    public var isSignedIn: Bool {
        if case .signedIn = self { return true }
        return false
    }
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
    public private(set) var state: AppAuthState = .restoring {
        didSet {
            // Any exit from a signed-in session (sign-out, REST 401, WS 4001,
            // failed restore) tears down that session's per-user state.
            if case .signedIn = oldValue, !state.isSignedIn { onSessionEnded?() }
        }
    }

    /// Set by `AppEnvironment`: disconnects the studio and drops user-scoped caches.
    @ObservationIgnored
    public var onSessionEnded: (@MainActor () -> Void)?

    private let environment: CodeMonetEnvironment
    private let controller: AuthenticationController
    /// Deferred rather than built in `init` so its `TokenProviding`
    /// conformance can reference `self` directly. This replaces an earlier
    /// `TokenBox` seam that started with a `{ nil }` placeholder closure and
    /// got "wired up" to the real token accessor after `init` returned —
    /// `lazy var` gets the same "only usable after full initialization"
    /// guarantee for free (a lazy initializer only ever runs on first
    /// access, and nothing in this class reads `restClient` before `init`
    /// returns), with no placeholder step. `WeakTokenProvider` still holds
    /// `self` weakly: an eager, strongly-self-capturing token provider
    /// stored on `self` (via `restClient`) would be a retain cycle, since
    /// `restClient` never leaves this instance.
    ///
    /// `@ObservationIgnored`: an implementation-detail dependency, not
    /// UI-observable state — and required here regardless, since `@Observable`
    /// rewrites tracked stored properties into macro-synthesized accessors
    /// that `lazy` cannot attach to.
    @ObservationIgnored
    private lazy var restClient = CodeMonetRESTClient(
        baseURL: environment.apiBaseURL,
        tokenProvider: WeakTokenProvider(auth: self)
    )
    /// DEBUG-only, never persisted (net-auth spec §4) — never routed through
    /// `AuthenticationController`'s refresh machinery.
    private var debugToken: String?

    public init(environment: CodeMonetEnvironment) {
        self.environment = environment
        let identityAPI = MobileAPIClient(baseURL: CodeMonetEnvironment.identityBaseURL)
        let codeMonetAPI = MobileAPIClient(baseURL: environment.apiBaseURL)
        let client = FentonIdentityClient(
            identityAPI: identityAPI,
            clientID: "net.dmfenton.codemonet",
            redirectURI: "https://monet.dmfenton.net/auth/callback",
            fetchIdentity: { bearerToken in
                let data = try await codeMonetAPI.data(path: "/auth/me", bearerToken: bearerToken)
                let user = try codeMonetAPI.decode(data, as: IdentityUserResponse.self)
                return HouseholdIdentity(actorID: user.id, email: user.email, householdID: nil, householdName: nil)
            }
        )
        let stores = KeychainAuthenticationStores(service: "net.dmfenton.sketchpad")
        controller = AuthenticationController(
            client: client,
            sessionStore: stores.session,
            pendingAuthorizationStore: stores.pendingAuthorization
        )
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

    /// Call when the app returns to the foreground (ux spec §1.2, net-auth
    /// spec §9.2 point 1): proactively re-validates/refreshes the cached
    /// platform session so a near-expiry token gets rotated before it ever
    /// causes a live WS `4001`/REST `401`. A genuine improvement over the RN
    /// app, which has no foreground-refresh hook at all — this is safe
    /// thanks to §3.3's `expiresAt` fix, which lets `AuthenticationController
    /// .restoreSession()` skip the network round-trip whenever the cached
    /// token is still comfortably valid.
    ///
    /// No-op when signed out/erroring (nothing to refresh) or when running
    /// on the DEBUG dev-token session (net-auth spec §4): that token isn't
    /// controller-backed and the server issues no refresh token for it, so
    /// calling `controller.restoreSession()` here would just read the
    /// *controller's* own (signed-out) state and incorrectly clobber
    /// `state` back to `.signedOut`.
    ///
    /// After this returns, the app shell should call `StudioStore
    /// .reconnectWithLatestToken()` so a rotated token opens a fresh socket
    /// (net-auth spec §9.1) rather than leaving a live connection on a
    /// now-stale one.
    public func refreshSessionOnForeground() async {
        guard debugToken == nil else { return }
        guard case .signedIn = state else { return }
        await controller.restoreSession()
        await syncStateFromController()
    }

    /// Progress and the "check your email" confirmation stay local to
    /// `AuthView`; the global state remains `.signedOut` so the form is not
    /// replaced (and its confirmation lost) while the request is in flight.
    public func requestMagicLink(email: String) async throws {
        _ = try await controller.requestMagicLink(email: email)
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

    /// Signs out only if `expected` still matches the bearer token
    /// currently in use — net-auth spec §9.2 point 2's
    /// `signOut(ifTokenMatches:)` pattern (`FentonMobileCore
    /// .AuthenticationController` has the equivalent
    /// `signOut(ifBearerTokenMatches:)`, but that only clears *its own*
    /// session; this wraps `AuthService.signOut()` instead so the DEBUG
    /// dev-token and `state` also get cleared consistently). Guards
    /// against a delayed WS auth-failure event from a socket already
    /// abandoned by a newer reconnect holding a freshly rotated, valid
    /// token — that stale event must not sign out a session that's
    /// actually fine.
    public func signOut(ifBearerTokenMatches expected: String) async {
        guard bearerToken == expected else { return }
        await signOut()
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
    /// Only a definitive 401/403 signs out; no verdict (offline, 5xx such as
    /// the server's 503 during an identity outage) keeps the session and retries.
    private func verifyIdentityMapping() async {
        var delay: Duration = .seconds(2)
        while !Task.isCancelled {
            do {
                let user = try await restClient.currentUser()
                state = .signedIn(user)
                return
            } catch MobileAPIError.unauthorized {
                await controller.signOut()
                state = .error("Identity could not be mapped to a CodeMonet user")
                return
            } catch {
                // No verdict: keep an existing signed-in session as is.
                if !state.isSignedIn { state = .restoring }
                try? await Task.sleep(for: delay)
                delay = min(delay * 2, .seconds(30))
            }
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

/// Reads `AuthService.bearerToken` (debug token, if any, else the
/// controller's platform session) without retaining it — see the doc
/// comment on `AuthService.restClient`. `@unchecked Sendable`: the only
/// stored property is a `weak` reference, and the one method that reads it
/// is `async`, so every call goes through the normal actor-hop Swift already
/// inserts for a call into a `@MainActor` type — never a raw concurrent read.
private struct WeakTokenProvider: TokenProviding, @unchecked Sendable {
    weak var auth: AuthService?
    func currentToken() async -> String? {
        await auth?.bearerToken
    }
}

/// CodeMonet's `GET /auth/me` response shape — app-specific, so it stays
/// here rather than in the shared `FentonIdentityClient` (net-auth spec
/// §0.2, §3.1).
private struct IdentityUserResponse: Decodable {
    let id: String
    let email: String
    let isActive: Bool
    enum CodingKeys: String, CodingKey {
        case id, email
        case isActive = "is_active"
    }
}
