import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// Dispatches one `AgentMessage` to its presentation (ux spec §6.3: 5
/// message-type presentations, all left-accent-bar cards except
/// `.iteration`'s centered pill).
struct MessageBubbleView: View {
    let message: AgentMessage

    var body: some View {
        Group {
            switch message.type {
            case .iteration:
                IterationPill(message: message)
            case .error:
                ErrorBubble(message: message)
            case .pieceComplete:
                PieceCompleteBubble(message: message)
            case .codeExecution:
                CodeExecutionBubble(message: message)
            case .thinking, .thinkingDelta:
                ThinkingBubble(message: message)
            }
        }
        .transition(.opacity.combined(with: .move(edge: .top)))
    }
}

/// `MessageIteration` — a small centered pill, not a full bubble.
private struct IterationPill: View {
    let message: AgentMessage

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        HStack(spacing: FentonSpacing.extraSmall) {
            Image(systemName: "repeat")
                .font(.system(size: 12))
                .accessibilityHidden(true)
            Text(message.text)
                .font(.caption)
        }
        .foregroundStyle(palette.tertiaryText)
        .opacity(0.7)
        .padding(.horizontal, FentonSpacing.small)
        .padding(.vertical, FentonSpacing.extraSmall)
        .frame(maxWidth: .infinity)
        .background(Capsule().fill(palette.subtleSurface))
    }
}

/// `MessageError` — red left-border, monospace `stderr` detail if present.
private struct ErrorBubble: View {
    let message: AgentMessage

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        MessageBubbleShell(borderColor: CodeMonetDesignSystem.Extra.error) {
            VStack(alignment: .leading, spacing: FentonSpacing.extraSmall) {
                HStack(alignment: .top, spacing: FentonSpacing.small) {
                    Image(systemName: "exclamationmark.circle.fill")
                        .foregroundStyle(CodeMonetDesignSystem.Extra.error)
                        .accessibilityHidden(true)
                    Text(message.text)
                        .font(.body)
                        .foregroundStyle(CodeMonetDesignSystem.Extra.error)
                }
                if let stderr = message.metadata?.stderr {
                    Text(stderr)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(palette.tertiaryText)
                }
                TimestampLabel(timestamp: message.timestamp, palette: palette)
            }
        }
    }
}

/// `MessagePieceComplete` — success-green left-border.
private struct PieceCompleteBubble: View {
    let message: AgentMessage

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        MessageBubbleShell(borderColor: palette.success) {
            VStack(alignment: .leading, spacing: FentonSpacing.extraSmall) {
                HStack(alignment: .top, spacing: FentonSpacing.small) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(palette.success)
                        .accessibilityHidden(true)
                    Text(message.text)
                        .font(.body)
                        .foregroundStyle(palette.success)
                }
                TimestampLabel(timestamp: message.timestamp, palette: palette)
            }
        }
    }
}

/// `MessageThinking` — the default/archived-thinking fallback.
private struct ThinkingBubble: View {
    let message: AgentMessage

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        MessageBubbleShell(borderColor: palette.accent) {
            VStack(alignment: .leading, spacing: FentonSpacing.extraSmall) {
                Text(message.text)
                    .font(.body)
                    .foregroundStyle(palette.text)
                TimestampLabel(timestamp: message.timestamp, palette: palette)
            }
        }
    }
}

/// `MessageCodeExecution` — tool-colored border, expandable output.
private struct CodeExecutionBubble: View {
    let message: AgentMessage

    @State private var expanded = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    private var toolName: String? { message.metadata?.toolName }
    private var isSuccess: Bool { (message.metadata?.returnCode ?? 0) == 0 }
    private var tool: StudioPresentation.ToolPresentation { StudioPresentation.presentation(forToolName: toolName) }
    private var isInProgress: Bool { StudioPresentation.isInProgress(messageText: message.text) }
    private var codePreview: String? {
        toolName == "generate_svg" ? StudioPresentation.code(fromToolInput: message.metadata?.toolInput) : nil
    }
    private var hasExpandableContent: Bool {
        message.metadata?.stdout != nil || message.metadata?.stderr != nil || codePreview != nil
    }

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        let borderColor = isSuccess ? StudioColors.color(for: tool.colorKey, palette: palette) : CodeMonetDesignSystem.Extra.error
        MessageBubbleShell(borderColor: borderColor) {
            VStack(alignment: .leading, spacing: FentonSpacing.small) {
                header(borderColor: borderColor)
                if expanded {
                    expandedContent(palette: palette)
                }
                TimestampLabel(timestamp: message.timestamp, palette: palette)
            }
        }
    }

    private func header(borderColor: Color) -> some View {
        Button {
            guard hasExpandableContent else { return }
            withAnimation(.easeInOut(duration: 0.15)) { expanded.toggle() }
        } label: {
            HStack(alignment: .top, spacing: FentonSpacing.small) {
                Image(systemName: isInProgress ? tool.activeIcon : tool.icon)
                    .foregroundStyle(borderColor)
                    .accessibilityHidden(true)
                Text(message.text)
                    .font(.body)
                    .foregroundStyle(theme.palette(for: colorScheme).text)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if hasExpandableContent {
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 12))
                        .foregroundStyle(theme.palette(for: colorScheme).tertiaryText)
                        .accessibilityHidden(true)
                }
            }
        }
        .buttonStyle(.plain)
        .disabled(!hasExpandableContent)
    }

    @ViewBuilder
    private func expandedContent(palette: FentonTheme.Palette) -> some View {
        if let codePreview {
            OutputSection(title: "Python Code", icon: "chevron.left.forwardslash.chevron.right", text: codePreview, palette: palette)
        }
        if let stdout = message.metadata?.stdout {
            OutputSection(title: "Output", icon: "terminal", text: stdout, palette: palette)
        }
        if let stderr = message.metadata?.stderr {
            OutputSection(title: "Error", icon: "exclamationmark.triangle", text: stderr, palette: palette, isError: true)
        }
    }
}

private struct OutputSection: View {
    let title: String
    let icon: String
    let text: String
    let palette: FentonTheme.Palette
    var isError = false

    var body: some View {
        VStack(alignment: .leading, spacing: FentonSpacing.extraSmall) {
            HStack(spacing: FentonSpacing.extraSmall) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundStyle(isError ? .red : palette.tertiaryText)
                    .accessibilityHidden(true)
                Text(title)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(isError ? .red : palette.tertiaryText)
            }
            ScrollView {
                Text(text)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(palette.secondaryText)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 150)
        }
        .padding(FentonSpacing.small)
        .background(RoundedRectangle(cornerRadius: FentonRadius.small, style: .continuous).fill(palette.surface))
    }
}

private struct TimestampLabel: View {
    let timestamp: Double
    let palette: FentonTheme.Palette

    var body: some View {
        Text(StudioPresentation.formatTime(epochMilliseconds: timestamp))
            .font(.caption2)
            .foregroundStyle(palette.tertiaryText)
            .frame(maxWidth: .infinity, alignment: .trailing)
    }
}

/// Shared left-accent-bar card shell (ux spec §6.3).
private struct MessageBubbleShell<Content: View>: View {
    let borderColor: Color
    @ViewBuilder let content: () -> Content

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        content()
            .padding(FentonSpacing.small)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: FentonRadius.small, style: .continuous).fill(palette.subtleSurface))
            .overlay(alignment: .leading) {
                Rectangle().fill(borderColor).frame(width: 3)
            }
            .clipShape(RoundedRectangle(cornerRadius: FentonRadius.small, style: .continuous))
    }
}
