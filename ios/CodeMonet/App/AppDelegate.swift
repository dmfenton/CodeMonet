import UIKit

/// Minimal `UIApplicationDelegate`. No push notifications today (ux/net-auth
/// specs explicitly scope those out — no server-side registration endpoint
/// exists yet); this exists as the documented seam for wiring
/// `FentonMobileCore.PushNotifications` if/when that becomes a real
/// requirement, and for any future launch-time configuration that needs to
/// run before SwiftUI's own lifecycle events fire.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        true
    }
}
