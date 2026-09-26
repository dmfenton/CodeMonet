import FentonDesignSystem
import SwiftUI

/// Code Monet's `FentonTheme.Palette` mapping (ux spec §9.1). The shared
/// package owns the 12 semantic slots; app-local colors that don't have a
/// Fenton slot (secondary/gold/coral/canvas/human-stroke/pen-indicator) are
/// defined as a small extension below, following Garden's
/// `DesignSystem.swift` convention of building app colors *on top of*
/// `FentonTheme` rather than modifying the shared package.
public enum CodeMonetDesignSystem {
    public static let theme = FentonTheme(
        light: FentonTheme.Palette(
            accent: Color(hex: "#e94560"),
            accentPressed: Color(hex: "#a83248"),
            emphasis: Color(hex: "#7b68ee"),
            surface: Color(hex: "#F5F5F8"),
            elevatedSurface: Color(hex: "#FFFFFF"),
            subtleSurface: Color(hex: "#FAFAFA"),
            text: Color(hex: "#1a1a2e"),
            secondaryText: Color(hex: "#4a4a6a"),
            tertiaryText: Color(hex: "#8888a8"),
            divider: Color(hex: "#e0e0e8"),
            success: Color(hex: "#4ade80"),
            warning: Color(hex: "#fbbf24")
        ),
        dark: FentonTheme.Palette(
            accent: Color(hex: "#e94560"),
            accentPressed: Color(hex: "#a83248"),
            emphasis: Color(hex: "#7b68ee"),
            surface: Color(hex: "#0a0a0f"),
            elevatedSurface: Color(hex: "#12121a"),
            subtleSurface: Color(hex: "#1a1a2e"),
            text: Color(hex: "#ffffff"),
            secondaryText: Color.white.opacity(0.7),
            tertiaryText: Color.white.opacity(0.4),
            divider: Color(hex: "#2a2a3e"),
            success: Color(hex: "#4ade80"),
            warning: Color(hex: "#fbbf24")
        )
    )

    /// App-local additions beyond `FentonTheme.Palette` (ux spec §9.1).
    /// Identical hex in both color schemes today (flagged in the spec as an
    /// intentional-but-unconfirmed choice, not silently "fixed" here).
    public enum Extra {
        public static let teal = Color(hex: "#4ecdc4")
        public static let gold = Color(hex: "#ffd93d")
        public static let coral = Color(hex: "#ff6b6b")
        public static let error = Color(hex: "#ef4444")
        /// The canvas paper stays white in both light and dark mode by design.
        public static let canvasBackground = Color(hex: "#FFFFFF")
        public static let strokeInk = Color(hex: "#1a1a2e")
        public static let humanStroke = Color(hex: "#7b68ee")
        public static let penIndicator = Color(hex: "#e94560")
    }
}

/// Presents a `.sheet` as a bottom detent sheet on compact width, or a
/// centered form sheet on regular width (ux spec §10 item 7: "definitely
/// allow ... a proper centered/form-sheet rather than a bottom sheet that
/// looks awkward at iPad width"). `StudioView`/`GalleryView` already branch
/// on `horizontalSizeClass == .regular` for their own iPad-specific
/// presentation; this gives sheet-presented modals (New Canvas, Nudge) the
/// same treatment via one shared modifier instead of duplicating the
/// detents/adaptation calls at each call site.
public struct AdaptiveSheetPresentation: ViewModifier {
    let isRegularWidth: Bool

    public init(isRegularWidth: Bool) {
        self.isRegularWidth = isRegularWidth
    }

    public func body(content: Content) -> some View {
        if isRegularWidth {
            // No `presentationDetents` here: adding one is what makes
            // iPadOS render a `.sheet` as a bottom-anchored resizable
            // detent sheet in the first place. Leaving it unset gives the
            // platform default for a regular-width presentation — a
            // centered form sheet — matching the RN app's own
            // `NewCanvasModal`-equivalent behavior on iPad.
            content
        } else {
            content
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }
}

extension Color {
    /// `#RRGGBB` hex parsing, tolerant of a missing `#`. Bad input falls back
    /// to opaque black rather than crashing — this is UI theming, not a
    /// server-trust boundary.
    init(hex: String) {
        var sanitized = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if sanitized.hasPrefix("#") { sanitized.removeFirst() }
        guard sanitized.count == 6, let value = UInt32(sanitized, radix: 16) else {
            self = .black
            return
        }
        let r = Double((value >> 16) & 0xFF) / 255.0
        let g = Double((value >> 8) & 0xFF) / 255.0
        let b = Double(value & 0xFF) / 255.0
        self = Color(red: r, green: g, blue: b)
    }
}
