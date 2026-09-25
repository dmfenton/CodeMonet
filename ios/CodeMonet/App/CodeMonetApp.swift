import FentonDesignSystem
import SwiftUI

/// App entry point. Launch-argument dev-token trigger (`-devToken`, per the
/// architect task) is read here and threaded to `AuthService` — see
/// `RootView`'s `.task` for where it's actually consumed.
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
