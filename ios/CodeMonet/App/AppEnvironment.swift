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
    @ObservationIgnored private var recoveryRetry: (token: String, task: Task<Void, Never>)?

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
        // Platform owns the refresh verdict. A rotated credential reconnects
        // the socket; a transient failure leaves the saved session intact.
        studio.onAuthenticationFailure = { [weak self] token in
            _ = await self?.recoverRejectedToken(token)
        }
        // Single teardown for every way a session ends (including feature
        // REST 401s): drop the old socket so the next sign-in can connect,
        // and forget the previous user's thumbnails.
        auth.onSessionEnded = { [weak self, weak studio] in
            self?.cancelRecoveryRetry()
            studio?.resetForSessionEnd()
            ThumbnailCache.shared.clear()
        }
    }

    /// Every app-owned authenticated surface passes a rejected bearer here.
    /// Platform owns the credential verdict; this app owns reconnecting its
    /// socket after rotation and retrying an inconclusive WebSocket rejection.
    func recoverRejectedToken(_ rejected: String) async -> String? {
        let replacement = await auth.recoverRejectedToken(rejected)
        guard let replacement else { return nil }
        if replacement != rejected {
            cancelRecoveryRetry()
            await studio.reconnectWithLatestToken()
        } else {
            scheduleRecoveryRetry(for: rejected)
        }
        return replacement
    }

    private func scheduleRecoveryRetry(for rejected: String) {
        if recoveryRetry?.token == rejected { return }
        cancelRecoveryRetry()
        let task = Task { @MainActor [weak self] in
            var delay: Duration = .seconds(2)
            while !Task.isCancelled {
                do { try await Task.sleep(for: delay) } catch { break }
                guard let self, self.auth.bearerToken == rejected else { break }
                let replacement = await self.auth.recoverRejectedToken(rejected)
                if let replacement, replacement != rejected {
                    await self.studio.reconnectWithLatestToken()
                    break
                }
                if replacement == nil { break }
                delay = min(delay * 2, .seconds(30))
            }
            self?.clearRecoveryRetry(for: rejected)
        }
        recoveryRetry = (rejected, task)
    }

    private func clearRecoveryRetry(for token: String) {
        if recoveryRetry?.token == token { recoveryRetry = nil }
    }

    private func cancelRecoveryRetry() {
        recoveryRetry?.task.cancel()
        recoveryRetry = nil
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
