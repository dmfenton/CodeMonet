import Foundation

/// Resolves the API/WS base URLs once at launch (net-auth spec §1). The WS
/// URL is **not** nested under `/api` — model it as an independently
/// configured base URL, never derived from `apiBaseURL`.
public struct CodeMonetEnvironment: Sendable, Equatable {
    public var apiBaseURL: URL
    public var wsBaseURL: URL
    /// Fixed across all environments — no dev/staging variant exists
    /// (net-auth spec §1).
    public static let identityBaseURL = URL(string: "https://identity.dmfenton.net")!

    public init(apiBaseURL: URL, wsBaseURL: URL) {
        self.apiBaseURL = apiBaseURL
        self.wsBaseURL = wsBaseURL
    }

    /// Release/TestFlight/App Store config (net-auth spec §1 table).
    public static let production = CodeMonetEnvironment(
        apiBaseURL: URL(string: "https://monet.dmfenton.net/api")!,
        wsBaseURL: URL(string: "wss://monet.dmfenton.net/ws")!
    )

    /// Debug/simulator default. `Info.plist` overrides
    /// (`CODE_MONET_API_BASE_URL`/`CODE_MONET_WS_BASE_URL`) let a developer
    /// point at a LAN IP for physical-device testing (net-auth spec §1).
    public static let debugLocalhost = CodeMonetEnvironment(
        apiBaseURL: URL(string: "http://localhost:8000")!,
        wsBaseURL: URL(string: "ws://localhost:8000/ws")!
    )

    /// Resolves the environment for this build: `.production` in Release,
    /// `.debugLocalhost` (optionally overridden by the two Info.plist keys
    /// above) in Debug. The app target's `AppConfig` calls this with the
    /// actual bundle so tests can inject a fake bundle.
    public static func resolve(infoDictionary: [String: Any]?) -> CodeMonetEnvironment {
        #if DEBUG
            var env = debugLocalhost
            if let apiOverride = infoDictionary?["CODE_MONET_API_BASE_URL"] as? String,
               !apiOverride.isEmpty, let url = URL(string: apiOverride) {
                env.apiBaseURL = url
            }
            if let wsOverride = infoDictionary?["CODE_MONET_WS_BASE_URL"] as? String,
               !wsOverride.isEmpty, let url = URL(string: wsOverride) {
                env.wsBaseURL = url
            }
            return env
        #else
            return production
        #endif
    }
}
