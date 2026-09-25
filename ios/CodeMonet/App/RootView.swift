import FentonMobileCore
import SwiftUI

/// Root gating (ux spec §1): auth-loading spinner -> Auth screen -> the
/// main app (a one-shot Splash overlay, then Home/Studio/Gallery). This is
/// the app-shell work package's file; feature views below are owned by
/// their respective packages per ../../ARCHITECTURE.md's ownership table.
struct RootView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.scenePhase) private var scenePhase
    @State private var deepLinkCoordinator = DeepLinkCoordinator(parser: CodeMonetAuthDeepLink.parser)
    @State private var didFinishSplash = false

    /// Net-auth spec §9.2 wants a *silent* foreground session revalidation
    /// (`AuthenticationController.restoreSession()`, reachable only through
    /// `AuthService.start()`, which also flips `state` to `.restoring` for
    /// the duration). Once the app has shown the signed-in UI at least once,
    /// keep rendering it straight through a background `.restoring` pass
    /// instead of dropping back to `LoadingScreen` — this is what makes the
    /// re-used `start()` call behave silently from the user's perspective,
    /// entirely within this file, without needing a second entry point on
    /// `AuthService` (owned by the networking+auth package).
    @State private var hasSignedInOnce = false

    /// Ux spec §1.2: only auto-resume on foreground if the agent was
    /// actually running immediately before backgrounding *and* the user is
    /// still in Studio. Not persisted — a fresh launch always starts false.
    @State private var wasRunningBeforeBackground = false

    var body: some View {
        Group {
            switch environment.auth.state {
            case .restoring where hasSignedInOnce:
                MainAppView()
            case .restoring, .signingIn, .exchangingCode:
                LoadingScreen()
            case .signedOut, .error:
                AuthView()
            case .signedIn:
                if didFinishSplash {
                    MainAppView()
                } else {
                    SplashView { didFinishSplash = true }
                }
            }
        }
        .task { await environment.auth.start() }
        .onOpenURL { url in handleIncoming(url) }
        .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
            if let url = activity.webpageURL { handleIncoming(url) }
        }
        .onChange(of: environment.auth.state) { _, newState in
            if case .signedIn = newState { hasSignedInOnce = true }
        }
        .onChange(of: scenePhase) { oldPhase, newPhase in
            handleScenePhaseChange(from: oldPhase, to: newPhase)
        }
    }

    private func handleIncoming(_ url: URL) {
        guard case let .authorizationCode(code) = deepLinkCoordinator.receive(url) else { return }
        Task {
            do {
                try await environment.auth.consume(code: code)
            } catch {
                // Net-auth spec §5.1: same "verifying…" overlay UX as a
                // successful exchange, but on failure the copy from ux spec
                // §3 needs somewhere to land. `consume` throwing here means
                // `verifyIdentityMapping()` never ran, so `AuthService.state`
                // is left at `.exchangingCode` (would hang on the spinner
                // forever) — reset it via the existing public `signOut()`
                // and surface the mapped message through `AppEnvironment`.
                environment.magicLinkError = MagicLinkDeepLinkError.message(for: error)
                await environment.auth.signOut()
            }
        }
    }

    /// Ux spec §1.2 (foreground/background side effects) + net-auth spec
    /// §9.2 (foreground session revalidation). Only the transitions that
    /// matter to those specs are handled; `.inactive` (e.g. the app switcher
    /// snapshot, an incoming call banner) is intentionally a no-op, matching
    /// RN's background/foreground-only hooks.
    private func handleScenePhaseChange(from oldPhase: ScenePhase, to newPhase: ScenePhase) {
        switch newPhase {
        case .background:
            handleDidEnterBackground()
        case .active where oldPhase == .background:
            handleWillEnterForeground()
        default:
            break
        }
    }

    private func handleDidEnterBackground() {
        let inStudio = environment.navigation.screen == .studio
        wasRunningBeforeBackground = inStudio && !environment.studio.state.paused
        if inStudio {
            environment.studio.stopPlayback()
        }
        if !environment.studio.state.paused {
            environment.studio.send(.pause)
        }
    }

    private func handleWillEnterForeground() {
        // Net-auth spec §9.2 step 1: proactively catch a near-expiry token
        // before it causes a live 401/4001. Silent thanks to `hasSignedInOnce`
        // above — no spinner flash for an already-signed-in session.
        Task { await environment.auth.start() }

        guard environment.navigation.screen == .studio else { return }
        environment.studio.startPlayback()
        if wasRunningBeforeBackground {
            environment.studio.send(.resume(direction: nil))
        }
    }
}

/// Universal-link-only deep link (net-auth spec §5.1) — the `codemonet://`
/// custom scheme is registered in Info.plist for parity but intentionally
/// has no handler (net-auth spec §5.2: no reachable production code path
/// emits it).
enum CodeMonetAuthDeepLink {
    static let parser = DeepLinkParser<Never>.authorizationCode(
        callback: { url in
            url.scheme == "https" && url.host == "monet.dmfenton.net" && url.path == "/auth/callback"
        },
        route: { _ in nil }
    )
}

/// Ux spec §3's error copy for a failed magic-link exchange. A pure mapping
/// (no I/O) so it's unit-testable without a network stack — see
/// `CodeMonetTests`.
enum MagicLinkDeepLinkError {
    static func message(for error: Error) -> String {
        if let authError = error as? AuthenticationClientError {
            switch authError {
            case .invalidAuthorizationCode, .unauthorized:
                return "Invalid or expired link"
            case .missingPendingAuthorization:
                return "Sign-in request expired on this device"
            }
        }
        if isTransportFailure(error) {
            return "Network error"
        }
        return "Invalid or expired link"
    }

    private static func isTransportFailure(_ error: Error) -> Bool {
        if error is MobileTransportFailure { return true }
        if let apiError = error as? MobileAPIError, case .transport = apiError { return true }
        return false
    }
}

/// Bare full-screen spinner, no chrome (ux spec §1 root gating step 1).
private struct LoadingScreen: View {
    var body: some View {
        ProgressView()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(uiColor: .systemBackground))
    }
}

/// The current screen underneath the one-shot Splash overlay (ux spec §1,
/// §5-§8). Owned by the "app shell" package for the switch/plumbing; each
/// case's view is owned by its own feature package.
///
/// Also hosts the New Canvas sheet (ux spec §7.2, native improvement #1):
/// `NewCanvasView` itself is the home+gallery+new-canvas UI package's file,
/// but presenting it as a real `.sheet` with detents — and giving it a
/// reachable entry point — is app-shell/navigation plumbing, so it lives
/// here rather than inside `HomeView`.
private struct MainAppView: View {
    @Environment(AppEnvironment.self) private var environment

    var body: some View {
        screenContent
            .sheet(isPresented: newCanvasSheetBinding) {
                NewCanvasView()
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
            }
            .sensoryFeedback(.selection, trigger: environment.navigation.activeModal)
    }

    @ViewBuilder
    private var screenContent: some View {
        switch environment.navigation.screen {
        case .home:
            NavigationStack {
                HomeView()
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                environment.navigation.activeModal = .newCanvas
                            } label: {
                                Image(systemName: "plus.circle.fill")
                            }
                            .accessibilityIdentifier("home-new-canvas-button")
                            .accessibilityLabel("New Canvas")
                        }
                    }
            }
        case .studio:
            StudioView()
        case .gallery:
            GalleryView()
        }
    }

    private var newCanvasSheetBinding: Binding<Bool> {
        Binding(
            get: { environment.navigation.activeModal == .newCanvas },
            set: { isPresented in
                if !isPresented { environment.navigation.activeModal = nil }
            }
        )
    }
}
