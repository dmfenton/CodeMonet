import FentonDesignSystem
import SwiftUI

/// The floating pill bar of up to 5 icon+label buttons (ux spec §6.4). The
/// button *set* is dynamic (`StudioPresentation.actionBarButtons`); this
/// view only lays out and styles whatever set it is handed.
struct ActionBarView: View {
    let buttons: [StudioPresentation.ActionBarButton]
    let onTap: (StudioPresentation.ActionBarButton.Kind) -> Void

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        HStack(spacing: 2) {
            ForEach(buttons) { button in
                ActionBarButtonView(button: button, palette: palette) { onTap(button.kind) }
            }
        }
        .padding(FentonSpacing.extraSmall)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous))
        .shadow(color: Color.black.opacity(0.12), radius: 16, x: 0, y: 6)
        .accessibilityIdentifier("action-bar")
    }
}

private struct ActionBarButtonView: View {
    let button: StudioPresentation.ActionBarButton
    let palette: FentonTheme.Palette
    let action: () -> Void

    private var foreground: Color {
        if button.disabled { return palette.tertiaryText }
        return button.active ? palette.accent : palette.text
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 2) {
                Image(systemName: button.icon)
                    .font(.system(size: 20))
                    .accessibilityHidden(true)
                Text(button.label)
                    .font(.caption2)
            }
            .foregroundStyle(foreground)
            .frame(maxWidth: .infinity)
            .padding(.vertical, FentonSpacing.small)
            .background(
                RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous)
                    .fill(button.active ? palette.subtleSurface : Color.clear)
            )
        }
        .disabled(button.disabled)
        .opacity(button.disabled ? 0.4 : 1)
        .accessibilityIdentifier("action-\(button.kind.rawValue)")
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityAddTraits(.isButton)
    }

    private var accessibilityLabel: String {
        var parts = [button.label]
        if button.active { parts.append("on") }
        if button.disabled { parts.append("disabled") }
        return parts.joined(separator: ", ")
    }
}
