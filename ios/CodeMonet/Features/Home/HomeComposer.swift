import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// The single place a new piece starts: a multiline prompt, the two real
/// styles (Paint, Plotter), a canvas-size chip, Surprise me (no direction),
/// and Begin. Replaces the old New Canvas sheet and the "OR" split.
struct HomeComposer: View {
    @Environment(AppEnvironment.self) private var environment
    let connected: Bool
    let onStarted: () -> Void

    @State private var prompt = ""
    @State private var profile = CanvasSizeProfiles.standard
    @FocusState private var promptFocused: Bool

    private static let maxLength = 200

    /// The style lives in `StudioState.drawingStyle`, so the choice survives
    /// Home being recreated on every Home <-> Studio round trip.
    private var style: DrawingStyleType { environment.studio.state.drawingStyle }

    var body: some View {
        PaletteReader { palette in
            VStack(alignment: .leading, spacing: 10) {
                promptField(palette: palette)
                chips
                HStack {
                    Button(action: surpriseMe) {
                        Label("Surprise me", systemImage: "dice")
                            .font(MonetType.chip)
                            .foregroundStyle(palette.secondaryText)
                    }
                    .buttonStyle(.plain)
                    .disabled(!connected)
                    .opacity(connected ? 1 : 0.5)
                    .accessibilityIdentifier("home-surprise-me")
                    Spacer()
                    Button(action: begin) {
                        Label("Begin", systemImage: "paintbrush.pointed")
                    }
                    .buttonStyle(PrimaryCapsuleStyle())
                    .disabled(!HomeSelectors.canSubmit(prompt: prompt, connected: connected))
                    .accessibilityIdentifier("home-prompt-submit")
                }
                .padding(.top, 2)
            }
            .padding(12)
            .background(RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous).fill(palette.subtleSurface))
            .overlay(
                RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous)
                    .strokeBorder(promptFocused ? palette.accent.opacity(0.5) : palette.divider, lineWidth: 1)
            )
            .sensoryFeedback(.selection, trigger: style)
            .sensoryFeedback(.selection, trigger: profile)
        }
    }

    private func promptField(palette: FentonTheme.Palette) -> some View {
        TextField(
            "",
            text: $prompt,
            prompt: Text("A foggy harbor at first light, boats barely there…")
                .font(MonetType.proseItalic)
                .foregroundStyle(palette.tertiaryText),
            axis: .vertical
        )
        .font(MonetType.prose)
        .foregroundStyle(palette.text)
        .lineLimit(2 ... 6)
        .focused($promptFocused)
        .submitLabel(.return)
        .onChange(of: prompt) { _, newValue in
            if newValue.count > Self.maxLength { prompt = String(newValue.prefix(Self.maxLength)) }
        }
        .accessibilityLabel("Describe the piece")
        .accessibilityIdentifier("home-prompt-input")
    }

    private var chips: some View {
        HStack(spacing: 6) {
            styleChip(.paint, title: "Paint", systemImage: "paintpalette")
            styleChip(.plotter, title: "Plotter", systemImage: "pencil.tip")
            Menu {
                Picker("Canvas size", selection: $profile) {
                    ForEach(CanvasSizeProfiles.all) { candidate in
                        Text("\(candidate.label) · \(candidate.aspectLabel)").tag(candidate)
                    }
                }
            } label: {
                ChipLabel(text: "\(profile.label) \(profile.aspectLabel)", systemImage: "aspectratio")
            }
            .accessibilityLabel("Canvas size, \(profile.label)")
            .accessibilityIdentifier("home-size-menu")
            Spacer(minLength: 0)
        }
    }

    private func styleChip(_ candidate: DrawingStyleType, title: String, systemImage: String) -> some View {
        Button {
            environment.studio.setStyle(candidate)
        } label: {
            ChipLabel(text: title, systemImage: systemImage, selected: style == candidate)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(style == candidate ? .isSelected : [])
        .accessibilityIdentifier("home-style-\(candidate.rawValue)")
    }

    private func begin() {
        guard HomeSelectors.canSubmit(prompt: prompt, connected: environment.studio.connected) else { return }
        start(direction: prompt)
        prompt = ""
    }

    private func surpriseMe() {
        guard environment.studio.connected else { return }
        start(direction: nil)
    }

    private func start(direction: String?) {
        promptFocused = false
        environment.studio.startNewPiece(direction: direction, style: style, width: profile.width, height: profile.height)
        onStarted()
    }
}
