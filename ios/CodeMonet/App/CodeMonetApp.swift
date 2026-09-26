import FentonDesignSystem
import SwiftUI

/// App entry point.
///
/// A note on the `-devToken` launch argument `CodeMonetUITests` passes for
/// its live-server flows: `AuthService.start()` (net-auth spec §4) already
/// tries the DEBUG-only dev-token bootstrap unconditionally, the moment
/// `restoreSession()` leaves the app signed out — there's no separate gate
/// in `AuthService`'s frozen contract for a launch argument to flip. So
/// `-devToken` isn't read here; it's consumed by the UI test target itself,
/// purely as a marker for "this test expects a reachable local dev server
/// at `localhost:8000`" (see `CodeMonetUITests`'s `requiresLiveServer`).
@main
struct CodeMonetApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var environment = AppEnvironment()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(environment)
                .fentonTheme(CodeMonetDesignSystem.theme)
        }
    }
}
