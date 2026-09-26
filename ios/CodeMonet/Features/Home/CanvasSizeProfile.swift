import Foundation

/// The 5 canvas-size presets New Canvas offers (ux spec §7.2), single-select,
/// `standard` pre-selected by default. Exact dimensions match the RN
/// `NewCanvasModal.tsx` `CANVAS_PROFILES` table byte-for-byte.
struct CanvasSizeProfile: Identifiable, Equatable {
    let id: String
    let label: String
    let width: Int
    let height: Int
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
