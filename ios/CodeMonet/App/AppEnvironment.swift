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

    public init(config: CodeMonetEnvironment = AppConfig.environment) {
        self.config = config
        let auth = AuthService(environment: config)
        self.auth = auth
        studio = StudioStore(environment: config, tokenProvider: AuthServiceTokenProvider(auth: auth))
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
