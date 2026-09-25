import FentonMobileCore
import SwiftUI

/// Root gating (ux spec §1): auth-loading spinner -> Auth screen -> the
/// main app (a one-shot Splash overlay, then Home/Studio/Gallery). This is
/// the app-shell work package's file; feature views below are owned by
/// their respective packages per ../../ARCHITECTURE.md's ownership table.
struct RootView: View {
    @Environment(AppEnvironment.self) private var environment
    @State private var deepLinkCoordinator = DeepLinkCoordinator(parser: CodeMonetAuthDeepLink.parser)
    @State private var didFinishSplash = false

    var body: some View {
        Group {
            switch environment.auth.state {
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
    }

    private func handleIncoming(_ url: URL) {
        guard case let .authorizationCode(code) = deepLinkCoordinator.receive(url) else { return }
        Task { try? await environment.auth.consume(code: code) }
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
private struct MainAppView: View {
    @Environment(AppEnvironment.self) private var environment

    var body: some View {
        switch environment.navigation.screen {
        case .home:
            HomeView()
        case .studio:
            StudioView()
        case .gallery:
            GalleryView()
        }
    }
}
