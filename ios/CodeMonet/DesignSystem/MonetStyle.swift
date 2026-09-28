import FentonDesignSystem
import SwiftUI

/// App-local type roles built from system fonts (no bundled font files):
/// serif (New York) for titles and prose, monospaced (SF Mono) for tool and
/// metadata lines, rounded/system for controls — the same split as
/// `FentonTypography`, which these complement for the redesign's roles.
enum MonetType {
    static let hero = Font.system(.title, design: .serif)
    static let heroTitle = Font.system(.title2, design: .serif).italic()
    static let screenTitle = Font.system(.largeTitle, design: .serif, weight: .medium)
    static let pieceTitle = Font.system(.headline, design: .serif, weight: .regular).italic()
    static let pieceTitleSmall = Font.system(.subheadline, design: .serif).italic()
    static let prose = Font.system(.subheadline, design: .serif)
    static let proseItalic = Font.system(.subheadline, design: .serif).italic()
    static let meta = Font.system(.caption, design: .monospaced)
    static let label = Font.system(.caption2, design: .monospaced, weight: .medium)
    static let chip = Font.system(.caption, design: .rounded, weight: .medium)
    static let button = Font.system(.subheadline, design: .rounded, weight: .semibold)
}

/// Resolves the current palette from the environment — one line instead of
/// the `theme.palette(for: colorScheme)` pair in every view.
struct PaletteReader<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme
    @ViewBuilder let content: (FentonTheme.Palette) -> Content

    var body: some View {
        content(theme.palette(for: colorScheme))
    }
}

/// A lowercase monospaced section label ("on the easel", "notebook").
struct SectionLabel: View {
    let text: String
    var color: Color?

    init(_ text: String, color: Color? = nil) {
        self.text = text
        self.color = color
    }

    var body: some View {
        PaletteReader { palette in
            Text(text)
                .font(MonetType.label)
                .tracking(0.5)
                .foregroundStyle(color ?? palette.tertiaryText)
        }
    }
}

/// A section label that runs into a hairline rule, with an optional
/// trailing element ("ON THE EASEL ——— mon, sep 28").
struct RuleLabel<Trailing: View>: View {
    let text: String
    @ViewBuilder var trailing: () -> Trailing

    init(_ text: String, @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }) {
        self.text = text
        self.trailing = trailing
    }

    var body: some View {
        PaletteReader { palette in
            HStack(alignment: .center, spacing: 10) {
                Text(text.uppercased())
                    .font(MonetType.label)
                    .tracking(1)
                    .foregroundStyle(palette.tertiaryText)
                    .accessibilityAddTraits(.isHeader)
                Rectangle().fill(palette.divider).frame(height: 1)
                trailing()
            }
        }
    }
}

/// A framed-picture mat for the hero piece: a wide mat, a fine bevel line
/// around the image, and a soft hanging shadow. The image keeps its own
/// colors; the mat follows the color scheme (dark linen in dark mode).
struct MuseumMat: ViewModifier {
    var padding: CGFloat = 14
    @Environment(\.colorScheme) private var colorScheme

    func body(content: Content) -> some View {
        PaletteReader { palette in
            let dark = colorScheme == .dark
            content
                .clipShape(RoundedRectangle(cornerRadius: 1.5, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                        .strokeBorder(Color.black.opacity(dark ? 0.5 : 0.12), lineWidth: 0.5)
                )
                .padding(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 2.5, style: .continuous)
                        .strokeBorder(palette.divider.opacity(dark ? 1 : 0.8), lineWidth: 1)
                )
                .padding(padding - 4)
                .background(
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                        .fill(palette.elevatedSurface)
                        .shadow(color: dark ? .black.opacity(0.5) : Self.shadowInk.opacity(0.08), radius: 1, y: 1)
                        .shadow(color: dark ? .black.opacity(0.6) : Self.shadowInk.opacity(0.2), radius: 16, y: 10)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                        .strokeBorder(palette.divider.opacity(dark ? 0.9 : 0.35), lineWidth: 0.5)
                )
        }
    }

    /// A warm umber so light-mode shadows read as paper, not grey plastic;
    /// on dark surfaces it would glow, so dark mode uses black.
    private static let shadowInk = Color(hex: "#3c2d14")
}

/// The paper mat every piece sits in: a thin subtle border around light
/// canvas paper, which stays light in dark mode.
struct PaperMat: ViewModifier {
    var padding: CGFloat = 6

    func body(content: Content) -> some View {
        PaletteReader { palette in
            content
                .background(CodeMonetDesignSystem.Extra.canvasBackground)
                .clipShape(RoundedRectangle(cornerRadius: 2, style: .continuous))
                .padding(padding)
                .background(
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .fill(palette.subtleSurface)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .strokeBorder(palette.divider, lineWidth: 1)
                )
        }
    }
}

extension View {
    func paperMat(padding: CGFloat = 6) -> some View {
        modifier(PaperMat(padding: padding))
    }

    func museumMat(padding: CGFloat = 14) -> some View {
        modifier(MuseumMat(padding: padding))
    }
}

/// A capsule chip; selected chips are tinted with the accent.
struct ChipLabel: View {
    let text: String
    var systemImage: String?
    var selected = false
    var monospaced = false

    var body: some View {
        PaletteReader { palette in
            HStack(spacing: 4) {
                if let systemImage {
                    Image(systemName: systemImage)
                        .imageScale(.small)
                        .accessibilityHidden(true)
                }
                Text(text)
                    .font(monospaced ? MonetType.meta : MonetType.chip)
            }
            .lineLimit(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .foregroundStyle(selected ? palette.accent : palette.secondaryText)
            .background(Capsule().fill(selected ? palette.accent.opacity(0.12) : Color.clear))
            .overlay(Capsule().strokeBorder(selected ? palette.accent : palette.divider, lineWidth: 1))
            .contentShape(Capsule())
        }
    }
}

/// The filled accent capsule used for primary actions (Watch, Continue).
struct PrimaryCapsuleStyle: ButtonStyle {
    /// `large` is the 46pt hero-action height.
    var large = false

    func makeBody(configuration: Configuration) -> some View {
        PrimaryCapsuleBody(configuration: configuration, large: large)
    }

    private struct PrimaryCapsuleBody: View {
        let configuration: ButtonStyleConfiguration
        let large: Bool
        @Environment(\.isEnabled) private var isEnabled

        var body: some View {
            PaletteReader { palette in
                configuration.label
                    .font(large ? .system(.body, design: .rounded, weight: .semibold) : MonetType.button)
                    .padding(.horizontal, large ? 20 : 16)
                    .frame(minHeight: large ? 46 : 36)
                    .foregroundStyle(isEnabled ? palette.surface : palette.tertiaryText)
                    .background(
                        Capsule().fill(
                            isEnabled
                                ? (configuration.isPressed ? palette.accentPressed : palette.accent)
                                : palette.subtleSurface
                        )
                    )
                    .overlay(Capsule().strokeBorder(isEnabled ? Color.clear : palette.divider, lineWidth: 1))
            }
        }
    }
}

/// A gentle press-down scale for chips, cards, and round buttons.
struct PressScaleStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// A round icon button with a hairline border (pause/resume, menus).
struct CircleIconLabel: View {
    let systemImage: String
    var size: CGFloat = 36

    var body: some View {
        PaletteReader { palette in
            Image(systemName: systemImage)
                .font(.system(size: size * 0.4, weight: .semibold))
                .foregroundStyle(palette.secondaryText)
                .frame(width: size, height: size)
                .background(Circle().fill(palette.surface))
                .overlay(Circle().strokeBorder(palette.divider, lineWidth: 1))
                .contentShape(Circle())
                .accessibilityHidden(true)
        }
    }
}
