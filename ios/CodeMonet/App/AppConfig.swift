import Foundation
import MonetNetworking

/// Thin wrapper resolving `CodeMonetEnvironment` from the running app's own
/// `Info.plist` (net-auth spec §1, §7). Exists so `AppEnvironment` doesn't
/// need to know about `Bundle` directly, and so tests can construct a
/// `CodeMonetEnvironment` without touching `Bundle.main`.
public enum AppConfig {
    public static var environment: CodeMonetEnvironment {
        CodeMonetEnvironment.resolve(infoDictionary: Bundle.main.infoDictionary)
    }
}
