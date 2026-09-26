import FentonDesignSystem
import Foundation
import MonetNetworking
import Observation

/// The app's dependency-injection root (per ARCHITECTURE.md's ownership
/// table, owned by the "app shell" work package). One instance is created
/// in `CodeMonetApp` and threaded down via `@Environment`/`@State`, so
/// feature views depend on protocols/services, never on `Bundle.main` or
/// singletons directly — this is what makes `CodeMonetUITests`' DEBUG
/// dev-token path and future unit tests able to substitute fakes.
@MainActor
@Observable
public final class AppEnvironment {
    public let config: CodeMonetEnvironment
    public let auth: AuthService
    public let studio: StudioStore
    public let navigation = NavigationState()

    /// A magic-link deep-link failure (ux spec §3's `magicLinkError` prop),
    /// carried from `RootView`'s deep-link handling into `AuthView` without
    /// AuthView needing to know about `DeepLinkCoordinator`. Cleared by
    /// `AuthView` on any user interaction with the email field, per spec.
    public var magicLinkError: String?

    public init(config: CodeMonetEnvironment = AppConfig.environment) {
        self.config = config
        let auth = AuthService(environment: config)
        self.auth = auth
        let studio = StudioStore(environment: config, tokenProvider: AuthServiceTokenProvider(auth: auth))
        self.studio = studio
        // Net-auth spec §9.2 point 2: a live 4001 close means the cached
        // session is no longer valid server-side — sign the user out so
        // RootView drops back to AuthView rather than sitting on a dead
        // socket. StudioStore only knows `TokenProviding`, never the
        // concrete `AuthService`, so this wiring has to happen here.
        // `ifBearerTokenMatches` guards against a delayed 4001 from a
        // socket already superseded by a reconnect with a valid, rotated
        // token (see `AuthService.signOut(ifBearerTokenMatches:)`).
        studio.onAuthenticationFailure = { [weak auth] token in
            await auth?.signOut(ifBearerTokenMatches: token)
        }
        // Single teardown for every way a session ends (including feature
        // REST 401s): drop the old socket so the next sign-in can connect,
        // and forget the previous user's thumbnails.
        auth.onSessionEnded = { [weak studio] in
            studio?.resetForSessionEnd()
            ThumbnailCache.shared.clear()
        }
    }
}

/// Adapts `AuthService`'s `@MainActor`-isolated `bearerToken` to
/// `MonetNetworking.TokenProviding`, which callers may invoke off the main
/// actor (e.g. from a background `URLSession` delegate queue).
private struct AuthServiceTokenProvider: TokenProviding {
    let auth: AuthService
    func currentToken() async -> String? {
        await auth.bearerToken
    }
}
