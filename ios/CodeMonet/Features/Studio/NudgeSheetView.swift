import FentonDesignSystem
import SwiftUI

/// "Send a Nudge" sheet (ux spec §7.1). A real `.sheet` with detents rather
/// than the RN app's fake bottom-sheet-with-a-decorative-handle (ux spec
/// §10.1's native improvement) — presented from `StudioView` via
/// `.sheet(isPresented:)`.
struct NudgeSheetView: View {
    let onSend: (String) -> Void
    let onDismiss: () -> Void

    @State private var text = ""
    @FocusState private var inputFocused: Bool
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    private static let quickSuggestions = [
        "Add some curves",
        "Try something bold",
        "More detail please",
        "Experiment freely",
    ]
    private static let maxLength = 200

    private var trimmed: String { text.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var remaining: Int { Self.maxLength - text.count }

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        NavigationStack {
            VStack(alignment: .leading, spacing: FentonSpacing.large) {
                suggestions(palette: palette)
                inputField(palette: palette)
                sendButton(palette: palette)
                Spacer(minLength: 0)
            }
            .padding(.top, FentonSpacing.large)
            .padding(.horizontal, FentonSpacing.large)
            .navigationTitle("Send a Nudge")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Text("Suggest something to the agent")
                        .font(.caption)
                        .foregroundStyle(palette.secondaryText)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        cancel()
                    } label: {
                        Image(systemName: "xmark")
                            .accessibilityHidden(true)
                    }
                    .accessibilityIdentifier("nudge-close-button")
                    .accessibilityLabel("Close")
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .onAppear { inputFocused = true }
    }

    private func suggestions(palette: FentonTheme.Palette) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: FentonSpacing.small) {
                ForEach(Self.quickSuggestions, id: \.self) { suggestion in
                    Button {
                        text = suggestion
                    } label: {
                        Text(suggestion)
                            .font(.caption)
                            .foregroundStyle(palette.secondaryText)
                            .padding(.horizontal, FentonSpacing.medium)
                            .padding(.vertical, FentonSpacing.small)
                            .background(Capsule().fill(palette.subtleSurface))
                    }
                }
            }
        }
    }

    private func inputField(palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .trailing, spacing: FentonSpacing.extraSmall) {
            TextField("Type your suggestion...", text: $text, axis: .vertical)
                .focused($inputFocused)
                .lineLimit(4 ... 8)
                .padding(FentonSpacing.medium)
                .background(RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous).fill(palette.subtleSurface))
                .accessibilityIdentifier("nudge-input")
                .onChange(of: text) {
                    if text.count > Self.maxLength { text = String(text.prefix(Self.maxLength)) }
                }
            Text("\(remaining)")
                .font(.caption2)
                .foregroundStyle(remaining < 20 ? palette.warning : palette.tertiaryText)
        }
    }

    private func sendButton(palette: FentonTheme.Palette) -> some View {
        Button {
            send()
        } label: {
            Label("Send Nudge", systemImage: "paperplane.fill")
                .font(.body.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, FentonSpacing.medium)
                .foregroundStyle(trimmed.isEmpty ? palette.tertiaryText : Color.white)
                .background(
                    RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous)
                        .fill(trimmed.isEmpty ? palette.subtleSurface : palette.accent)
                )
        }
        .disabled(trimmed.isEmpty)
        .sensoryFeedback(.success, trigger: didSend)
        .accessibilityIdentifier("nudge-send-button")
    }

    @State private var didSend = false

    private func send() {
        guard !trimmed.isEmpty else { return }
        onSend(trimmed)
        didSend.toggle()
        text = ""
        onDismiss()
    }

    private func cancel() {
        text = ""
        onDismiss()
    }
}
