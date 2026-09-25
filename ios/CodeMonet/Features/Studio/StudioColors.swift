import FentonDesignSystem
import SwiftUI

/// Maps `StudioPresentation.ToolColorKey` to an actual `Color` (ux spec
/// §6.1's per-tool border color table). Kept separate from
/// `StudioPresentation` so that file stays free of SwiftUI, and separate
/// from `CodeMonetDesignSystem` (app-shell-owned) since these are
/// Studio-local accents with no Fenton-palette slot.
enum StudioColors {
    /// Purple used for `generate_svg` (ux spec §6.1: `#8B5CF6`).
    static let generateSvgPurple = Color(hex: "#8B5CF6")
    /// Sky blue used for `critique_canvas` (ux spec §6.1: `#0EA5E9`).
    static let critiqueCanvasSky = Color(hex: "#0EA5E9")
    /// Amber used for `imagine` (ux spec §6.1: `#F59E0B`).
    static let imagineAmber = Color(hex: "#F59E0B")

    static func color(
        for key: StudioPresentation.ToolColorKey,
        palette: FentonTheme.Palette
    ) -> Color {
        switch key {
        case .primary: palette.accent
        case .purple: generateSvgPurple
        case .muted: palette.tertiaryText
        case .sky: critiqueCanvasSky
        case .success: palette.success
        case .amber: imagineAmber
        }
    }
}
