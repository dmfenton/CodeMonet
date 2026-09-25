import FentonDesignSystem
import SwiftUI

/// Always-visible display of current agent activity (ux spec §6.1). Renders
/// nothing when idle with no buffered content — its disappearance is the
/// signal the `agent-draw` e2e flow waits on for "agent finished".
struct LiveStatusView: View {
    let display: StudioPresentation.LiveStatusDisplay

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    private var palette: FentonTheme.Palette { theme.palette(for: colorScheme) }
    private var color: Color { StudioColors.color(for: display.colorKey, palette: palette) }

    var body: some View {
        VStack(alignment: .leading, spacing: FentonSpacing.small) {
            statusRow
            bodyContent
        }
        .padding(FentonSpacing.medium)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous).fill(palette.elevatedSurface))
        .shadow(color: Color.black.opacity(0.06), radius: 8, x: 0, y: 2)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("live-status")
        .accessibilityLabel(accessibilityText)
    }

    private var statusRow: some View {
        HStack(spacing: FentonSpacing.small) {
            Image(systemName: display.icon)
                .font(.system(size: 16))
                .foregroundStyle(color)
                .symbolEffect(.pulse, isActive: display.isActive)
                .accessibilityHidden(true)
                .accessibilityHidden(true)
            Text(display.label + (display.isActive ? "…" : ""))
                .font(.footnote.weight(.semibold))
                .foregroundStyle(color)
        }
    }

    @ViewBuilder
    private var bodyContent: some View {
        switch display.body {
        case .none:
            EmptyView()
        case let .event(icon, colorKey, text):
            eventBubble(icon: icon, color: StudioColors.color(for: colorKey, palette: palette), text: text)
        case let .thinking(text, isBuffering):
            thinkingText(text, isBuffering: isBuffering)
        }
    }

    private func eventBubble(icon: String, color: Color, text: String) -> some View {
        HStack(alignment: .top, spacing: FentonSpacing.small) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(color)
                .accessibilityHidden(true)
            Text(text)
                .font(.body)
                .foregroundStyle(palette.text)
                .lineLimit(2)
        }
        .padding(FentonSpacing.small)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: FentonRadius.small, style: .continuous)
                .fill(palette.subtleSurface)
        )
        .overlay(alignment: .leading) {
            Rectangle().fill(color).frame(width: 3)
        }
        .clipShape(RoundedRectangle(cornerRadius: FentonRadius.small, style: .continuous))
    }

    private func thinkingText(_ text: String, isBuffering: Bool) -> some View {
        (Text(text).foregroundStyle(palette.text) + Text(isBuffering ? " ▍" : "").foregroundStyle(palette.tertiaryText))
            .font(.body)
            .lineLimit(3)
            .lineSpacing(6)
    }

    private var accessibilityText: String {
        switch display.body {
        case .none:
            display.label
        case let .event(_, _, text):
            "\(display.label). \(text)"
        case let .thinking(text, _):
            text.isEmpty ? display.label : "\(display.label). \(text)"
        }
    }
}
