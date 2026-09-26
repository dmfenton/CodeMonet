import FentonDesignSystem
import SwiftUI

/// Studio's top bar: back, the piece title (serif italic), the status pill,
/// and a menu holding the rest of what the old action bar offered.
struct StudioTopBar: View {
    let title: String
    let pill: StudioPresentation.StatusPill
    let menu: StudioMenuState
    let onBack: () -> Void
    let onAction: (StudioMenuAction) -> Void

    var body: some View {
        PaletteReader { palette in
            HStack(spacing: 10) {
                Button(action: onBack) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(palette.secondaryText)
                        .frame(width: 32, height: 32)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel("Home")
                .accessibilityIdentifier("studio-back-button")

                Text(title)
                    .font(MonetType.pieceTitle)
                    .foregroundStyle(palette.text)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity)
                    .accessibilityIdentifier("studio-title")

                StatusPillView(pill: pill)
                StudioMenu(state: menu, onAction: onAction)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
        }
    }
}

struct StatusPillView: View {
    let pill: StudioPresentation.StatusPill

    var body: some View {
        PaletteReader { palette in
            HStack(spacing: 5) {
                Circle()
                    .fill(pill.isActive ? palette.emphasis : palette.tertiaryText)
                    .frame(width: 6, height: 6)
                    .symbolEffectPulse(pill.isActive)
                Text(pill.label)
                    .font(MonetType.label)
            }
            .foregroundStyle(pill.isActive ? palette.accent : palette.secondaryText)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(Capsule().fill(pill.isActive ? palette.accent.opacity(0.12) : palette.subtleSurface))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Status: \(pill.label)")
            .accessibilityIdentifier("status-pill")
        }
    }
}

private extension View {
    /// A gentle breathing pulse on the live dot while the agent works.
    func symbolEffectPulse(_ active: Bool) -> some View {
        phaseAnimator(active ? [1.0, 0.35] : [1.0]) { view, phase in
            view.opacity(phase)
        } animation: { _ in
            .easeInOut(duration: 0.9)
        }
    }
}

/// What the Studio menu can do right now.
struct StudioMenuState: Equatable {
    var paused: Bool
    var viewOnly: Bool
    var drawingEnabled: Bool
    var connected: Bool
    var galleryCount: Int
}

enum StudioMenuAction {
    case newPiece, gallery, toggleDrawing, togglePause
}

private struct StudioMenu: View {
    let state: StudioMenuState
    let onAction: (StudioMenuAction) -> Void

    var body: some View {
        Menu {
            Button("New piece", systemImage: "plus") { onAction(.newPiece) }
            Button("Gallery", systemImage: "photo.on.rectangle") { onAction(.gallery) }
                .disabled(state.galleryCount == 0)
            if !state.viewOnly {
                Button(
                    state.drawingEnabled ? "Stop drawing" : "Draw on canvas",
                    systemImage: state.drawingEnabled ? "pencil.slash" : "pencil.tip"
                ) { onAction(.toggleDrawing) }
                    .disabled(!state.connected || state.paused)
                Button(
                    state.paused ? "Resume painter" : "Pause painter",
                    systemImage: state.paused ? "play" : "pause"
                ) { onAction(.togglePause) }
                    .disabled(!state.connected)
            }
        } label: {
            CircleIconLabel(systemImage: "ellipsis", size: 32)
        }
        .accessibilityLabel("Studio menu")
        .accessibilityIdentifier("studio-menu")
    }
}

/// The always-visible nudge composer with the pause/resume button beside it.
struct NudgeBar: View {
    let paused: Bool
    let connected: Bool
    let onTogglePause: () -> Void
    let onSend: (String) -> Void

    @State private var text = ""
    @FocusState private var focused: Bool
    private static let maxLength = 200

    private var trimmed: String { text.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        PaletteReader { palette in
            HStack(spacing: 8) {
                Button(action: onTogglePause) {
                    CircleIconLabel(systemImage: paused ? "play.fill" : "pause.fill")
                }
                .disabled(!connected)
                .opacity(connected ? 1 : 0.5)
                .accessibilityLabel(paused ? "Resume painter" : "Pause painter")
                .accessibilityIdentifier("studio-pause-button")

                HStack(spacing: 6) {
                    TextField(
                        "",
                        text: $text,
                        prompt: Text("Nudge the painter…").font(MonetType.proseItalic).foregroundStyle(palette.tertiaryText),
                        axis: .vertical
                    )
                    .font(MonetType.prose)
                    .foregroundStyle(palette.text)
                    .lineLimit(1 ... 4)
                    .focused($focused)
                    .submitLabel(.send)
                    .onSubmit(send)
                    .onChange(of: text) { _, newValue in
                        if newValue.contains("\n") {
                            text = newValue.replacingOccurrences(of: "\n", with: "")
                            send()
                        } else if newValue.count > Self.maxLength {
                            text = String(newValue.prefix(Self.maxLength))
                        }
                    }
                    .accessibilityLabel("Nudge the painter")
                    .accessibilityIdentifier("nudge-input")

                    Button(action: send) {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(canSend ? palette.surface : palette.tertiaryText)
                            .frame(width: 28, height: 28)
                            .background(Circle().fill(canSend ? palette.accent : palette.divider))
                    }
                    .disabled(!canSend)
                    .accessibilityLabel("Send nudge")
                    .accessibilityIdentifier("nudge-send-button")
                }
                .padding(.leading, 14)
                .padding(.trailing, 4)
                .padding(.vertical, 4)
                .frame(minHeight: 36)
                .background(Capsule().fill(palette.subtleSurface))
                .overlay(Capsule().strokeBorder(focused ? palette.accent.opacity(0.5) : palette.divider, lineWidth: 1))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
        }
    }

    private var canSend: Bool { connected && !trimmed.isEmpty }

    private func send() {
        guard canSend else { return }
        onSend(trimmed)
        text = ""
    }
}
