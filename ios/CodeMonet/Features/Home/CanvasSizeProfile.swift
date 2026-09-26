import Foundation

/// The 5 canvas-size presets the Home composer's size chip offers,
/// single-select, `standard` pre-selected by default. Exact dimensions match
/// the RN `NewCanvasModal.tsx` `CANVAS_PROFILES` table byte-for-byte.
struct CanvasSizeProfile: Identifiable, Hashable {
    let id: String
    let label: String
    let width: Int
    let height: Int

    /// Reduced aspect ratio, e.g. "4:3" for 800x600.
    var aspectLabel: String {
        let divisor = Self.gcd(width, height)
        guard divisor > 0 else { return "\(width)×\(height)" }
        return "\(width / divisor):\(height / divisor)"
    }

    private static func gcd(_ a: Int, _ b: Int) -> Int {
        b == 0 ? a : gcd(b, a % b)
    }
}

enum CanvasSizeProfiles {
    static let standard = CanvasSizeProfile(id: "standard", label: "Standard", width: 800, height: 600)
    static let masthead = CanvasSizeProfile(id: "masthead", label: "Masthead", width: 1200, height: 420)
    static let square = CanvasSizeProfile(id: "square", label: "Square", width: 800, height: 800)
    static let portrait = CanvasSizeProfile(id: "portrait", label: "Portrait", width: 600, height: 900)
    static let wide = CanvasSizeProfile(id: "wide", label: "Wide", width: 1200, height: 600)

    /// Display order matches the RN chip row exactly.
    static let all: [CanvasSizeProfile] = [standard, masthead, square, portrait, wide]
}
