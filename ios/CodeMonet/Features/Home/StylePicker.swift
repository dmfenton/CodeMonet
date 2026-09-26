import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// Which visual treatment `StylePickerView` uses (ux spec §5.1 vs §7.2):
/// Home uses a single grouped "segmented" track, New Canvas uses
/// individually-colored "pills". Shared between `Features/Home` and
/// `Features/NewCanvas` (both owned by this work package).
public enum StylePickerVariant: Equatable {
    case segmented
    case pills
}

/// Plotter/Paint picker (ux spec §5.1 point 3, §7.2). Selects the style for
/// the *next* canvas only — never applied retroactively to a canvas already
/// in progress (ux spec §2).
struct StylePickerView: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    let label: String
    @Binding var selection: DrawingStyleType
    var variant: StylePickerVariant = .segmented
    var testIDPrefix: String = "style"

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        VStack(alignment: .leading, spacing: FentonSpacing.small) {
            Text(label)
                .font(FentonTypography.label)
                .foregroundStyle(palette.tertiaryText)

            HStack(spacing: variant == .segmented ? 0 : FentonSpacing.small) {
                option(.plotter, systemImage: "pencil", title: "Plotter", palette: palette)
                option(.paint, systemImage: "paintpalette", title: "Paint", palette: palette)
            }
            .padding(variant == .segmented ? FentonSpacing.extraSmall : 0)
            .background {
                if variant == .segmented {
                    RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous)
                        .fill(palette.subtleSurface)
                }
            }
            .sensoryFeedback(.selection, trigger: selection)
        }
    }

    @ViewBuilder
    private func option(_ style: DrawingStyleType, systemImage: String, title: String, palette: FentonTheme.Palette) -> some View {
        let isActive = selection == style
        Button {
            selection = style
        } label: {
            Label(title, systemImage: systemImage)
                .font(FentonTypography.body.weight(.medium))
                .frame(maxWidth: .infinity)
                .padding(.vertical, FentonSpacing.small)
                .foregroundStyle(optionForeground(isActive: isActive, palette: palette))
                .background(optionBackground(isActive: isActive, palette: palette))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("\(testIDPrefix)-\(style.rawValue)-button")
    }

    private func optionForeground(isActive: Bool, palette: FentonTheme.Palette) -> Color {
        switch variant {
        case .segmented:
            isActive ? palette.accent : palette.secondaryText
        case .pills:
            isActive ? .white : palette.secondaryText
        }
    }

    @ViewBuilder
    private func optionBackground(isActive: Bool, palette: FentonTheme.Palette) -> some View {
        switch variant {
        case .segmented:
            RoundedRectangle(cornerRadius: FentonRadius.small, style: .continuous)
                .fill(isActive ? palette.elevatedSurface : .clear)
                .shadow(color: .black.opacity(isActive ? 0.1 : 0), radius: 2, x: 0, y: 1)
        case .pills:
            Capsule()
                .fill(isActive ? palette.accent : palette.subtleSurface)
        }
    }
}

#Preview {
    @Previewable @State var style: DrawingStyleType = .plotter
    VStack(spacing: 24) {
        StylePickerView(label: "Style", selection: $style, variant: .segmented)
        StylePickerView(label: "Style", selection: $style, variant: .pills, testIDPrefix: "new-canvas-style")
    }
    .padding()
    .fentonTheme(CodeMonetDesignSystem.theme)
}
