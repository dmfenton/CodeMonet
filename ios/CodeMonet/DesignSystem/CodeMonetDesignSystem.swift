import FentonDesignSystem
import SwiftUI
import UIKit

/// Code Monet's `FentonTheme.Palette` mapping: the Fenton paper / ink /
/// forest palette (matches `brand/mark.svg` and the web client). The shared
/// package owns the 12 semantic slots; the few app-local colors without a
/// Fenton slot live in `Extra` below, built on top of the theme rather than
/// modifying the shared package.
public enum CodeMonetDesignSystem {
    public static let theme = FentonTheme(
        light: FentonTheme.Palette(
            accent: Color(hex: "#1f4d34"),
            accentPressed: Color(hex: "#0f2a1c"),
            emphasis: Color(hex: "#b85a2e"),
            surface: Color(hex: "#fdfbf5"),
            elevatedSurface: Color(hex: "#fffdf8"),
            subtleSurface: Color(hex: "#f8f3e7"),
            text: Color(hex: "#1a1d18"),
            secondaryText: Color(hex: "#5e6358"),
            tertiaryText: Color(hex: "#7a7f74"),
            divider: Color(hex: "#e2d5b3"),
            success: Color(hex: "#3a7a53"),
            warning: Color(hex: "#9a6a12")
        ),
        dark: FentonTheme.Palette(
            accent: Color(hex: "#8bbda1"),
            accentPressed: Color(hex: "#71ab8a"),
            emphasis: Color(hex: "#e07d4f"),
            surface: Color(hex: "#15160f"),
            elevatedSurface: Color(hex: "#1d1e16"),
            subtleSurface: Color(hex: "#2b2d23"),
            text: Color(hex: "#ece6d2"),
            secondaryText: Color(hex: "#b9b29c"),
            tertiaryText: Color(hex: "#8f8a79"),
            divider: Color(hex: "#3b3e31"),
            success: Color(hex: "#71ab8a"),
            warning: Color(hex: "#e3c07a")
        )
    )

    /// App-local colors with no `FentonTheme.Palette` slot.
    public enum Extra {
        /// The canvas paper stays light in both color schemes by design, so
        /// a painting always reads true.
        public static let canvasBackground = Color(hex: "#fffdf8")
        public static let strokeInk = Color(hex: "#1a1d18")
        /// Human marks on the canvas (rose). The canvas is always light
        /// paper, so this is a single, non-adaptive color.
        public static let humanStroke = Color(hex: "#9b4f45")
        /// The agent's pen position on the (always light) canvas: the light
        /// palette's emphasis.
        public static let penIndicator = theme.light.emphasis
        /// Error text/rules on app surfaces — adapts to the color scheme.
        public static let error = Color(light: "#9b4f45", dark: "#d98a7e")
    }
}

/// Presents a `.sheet` as a bottom detent sheet on compact width, or a
/// centered form sheet on regular width (ux spec §10 item 7).
public struct AdaptiveSheetPresentation: ViewModifier {
    let isRegularWidth: Bool

    public init(isRegularWidth: Bool) {
        self.isRegularWidth = isRegularWidth
    }

    public func body(content: Content) -> some View {
        if isRegularWidth {
            // No `presentationDetents`: that's what makes iPadOS render a
            // bottom-anchored detent sheet instead of a centered form sheet.
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
        self = Color(uiColor: UIColor(hex: hex))
    }

    /// A color that resolves per color scheme (for app-local extras that
    /// have no palette slot but still need a dark-mode value).
    init(light: String, dark: String) {
        let lightColor = UIColor(hex: light)
        let darkColor = UIColor(hex: dark)
        self = Color(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? darkColor : lightColor
        })
    }
}

private extension UIColor {
    convenience init(hex: String) {
        var sanitized = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if sanitized.hasPrefix("#") { sanitized.removeFirst() }
        guard sanitized.count == 6, let value = UInt32(sanitized, radix: 16) else {
            self.init(red: 0, green: 0, blue: 0, alpha: 1)
            return
        }
        self.init(
            red: CGFloat((value >> 16) & 0xFF) / 255.0,
            green: CGFloat((value >> 8) & 0xFF) / 255.0,
            blue: CGFloat(value & 0xFF) / 255.0,
            alpha: 1
        )
    }
}
