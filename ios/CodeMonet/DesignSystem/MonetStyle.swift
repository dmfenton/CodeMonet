import FentonDesignSystem
import SwiftUI

/// App-local type roles built from system fonts (no bundled font files):
/// serif (New York) for titles and prose, monospaced (SF Mono) for tool and
/// metadata lines, rounded/system for controls — the same split as
/// `FentonTypography`, which these complement for the redesign's roles.
enum MonetType {
    static let display = Font.system(.title2, design: .serif)
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

/// The filled accent capsule used for primary actions (Begin, Watch).
struct PrimaryCapsuleStyle: ButtonStyle {
    var compact = false

    func makeBody(configuration: Configuration) -> some View {
        PrimaryCapsuleBody(configuration: configuration, compact: compact)
    }

    private struct PrimaryCapsuleBody: View {
        let configuration: ButtonStyleConfiguration
        let compact: Bool
        @Environment(\.isEnabled) private var isEnabled

        var body: some View {
            PaletteReader { palette in
                configuration.label
                    .font(compact ? MonetType.chip.weight(.semibold) : MonetType.button)
                    .padding(.horizontal, compact ? 12 : 16)
                    .padding(.vertical, compact ? 6 : 9)
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
