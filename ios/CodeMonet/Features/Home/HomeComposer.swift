import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// The single place a new piece starts: a multiline prompt, the Paint /
/// Plotter toggle, a canvas-size chip, and a round send button, with a row
/// of one-tap ideas (led by Surprise me, no direction) underneath.
struct HomeComposer: View {
    @Environment(AppEnvironment.self) private var environment
    let connected: Bool
    /// A piece is on the easel, so starting a new one retires it to the gallery.
    let replacesEasel: Bool
    /// Reports prompt focus so Home can lift the composer above the keyboard.
    var onFocusChange: (Bool) -> Void = { _ in }
    let onStarted: () -> Void

    @State private var prompt = ""
    @State private var profile = CanvasSizeProfiles.standard
    @FocusState private var promptFocused: Bool
    @Namespace private var styleSelection

    private static let maxLength = 200

    /// The next piece's style. Composer-local so choosing it never restyles
    /// the piece on the easel; `startNewPiece` applies it when a piece
    /// starts. Defaults to the current piece's style.
    @State private var chosenStyle: DrawingStyleType?
    private var style: DrawingStyleType { chosenStyle ?? environment.studio.state.drawingStyle }
    private var canBegin: Bool { HomeSelectors.canSubmit(prompt: prompt, connected: connected) }

    var body: some View {
        PaletteReader { palette in
            VStack(alignment: .leading, spacing: 12) {
                card(palette: palette)
                if replacesEasel && promptFocused {
                    Text("the piece on the easel moves to your gallery")
                        .font(MonetType.meta)
                        .foregroundStyle(palette.tertiaryText)
                        .transition(.opacity)
                }
                ideas(palette: palette)
            }
            .animation(.easeOut(duration: 0.2), value: promptFocused)
            .onChange(of: promptFocused) { _, focused in onFocusChange(focused) }
            .sensoryFeedback(.selection, trigger: chosenStyle)
            .sensoryFeedback(.selection, trigger: profile)
        }
    }

    // MARK: - Card

    private func card(palette: FentonTheme.Palette) -> some View {
        let shape = RoundedRectangle(cornerRadius: 22, style: .continuous)
        return VStack(alignment: .leading, spacing: 12) {
            promptField(palette: palette)
            HStack(spacing: 8) {
                styleToggle(palette: palette)
                sizeMenu
                Spacer(minLength: 0)
                sendButton(palette: palette)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 16)
        .padding(.bottom, 12)
        // Tapping bare card (not a control) focuses the prompt.
        .background(shape.fill(palette.elevatedSurface).onTapGesture { promptFocused = true })
        .overlay(shape.strokeBorder(promptFocused ? palette.accent.opacity(0.55) : palette.divider, lineWidth: 1))
        .background(shape.inset(by: -4).fill(palette.accent.opacity(promptFocused ? 0.08 : 0)))
    }

    private func promptField(palette: FentonTheme.Palette) -> some View {
        TextField(
            "",
            text: $prompt,
            prompt: Text("A foggy harbor at first light…")
                .font(.system(.body, design: .serif).italic())
                .foregroundStyle(palette.tertiaryText),
            axis: .vertical
        )
        .font(.system(.body, design: .serif))
        .foregroundStyle(palette.text)
        .tint(palette.accent)
        .lineLimit(2 ... 6)
        .focused($promptFocused)
        .submitLabel(.return)
        .onChange(of: prompt) { _, newValue in
            if newValue.count > Self.maxLength { prompt = String(newValue.prefix(Self.maxLength)) }
        }
        .accessibilityLabel("Describe the piece")
        .accessibilityIdentifier("home-prompt-input")
    }

    /// Paint | Plotter as one segmented capsule; the selection slides.
    private func styleToggle(palette: FentonTheme.Palette) -> some View {
        HStack(spacing: 0) {
            styleSegment(.paint, title: "Paint", systemImage: "paintpalette", palette: palette)
            styleSegment(.plotter, title: "Plotter", systemImage: "pencil.tip", palette: palette)
        }
        .padding(3)
        .background(Capsule().fill(palette.subtleSurface))
        .overlay(Capsule().strokeBorder(palette.divider, lineWidth: 1))
        .animation(.spring(response: 0.3, dampingFraction: 0.85), value: style)
    }

    private func styleSegment(
        _ candidate: DrawingStyleType, title: String, systemImage: String, palette: FentonTheme.Palette
    ) -> some View {
        let selected = style == candidate
        return Button {
            chosenStyle = candidate
        } label: {
            Label(title, systemImage: systemImage)
                .labelStyle(.titleAndIcon)
                .font(MonetType.chip)
                .imageScale(.small)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .foregroundStyle(selected ? palette.accent : palette.secondaryText)
                .background {
                    if selected {
                        Capsule()
                            .fill(palette.elevatedSurface)
                            .shadow(color: .black.opacity(0.1), radius: 1.5, y: 1)
                            .matchedGeometryEffect(id: "style", in: styleSelection)
                    }
                }
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("home-style-\(candidate.rawValue)")
    }

    /// The size chip draws the chosen aspect ratio as its icon.
    private var sizeMenu: some View {
        Menu {
            Picker("Canvas size", selection: $profile) {
                ForEach(CanvasSizeProfiles.all) { candidate in
                    Text("\(candidate.label) · \(candidate.aspectLabel)").tag(candidate)
                }
            }
        } label: {
            PaletteReader { palette in
                HStack(spacing: 5) {
                    AspectGlyph(width: profile.width, height: profile.height)
                        .stroke(palette.secondaryText, lineWidth: 1.2)
                        .frame(width: 14, height: 14)
                    Text(profile.aspectLabel)
                        .font(MonetType.chip)
                }
                .foregroundStyle(palette.secondaryText)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .overlay(Capsule().strokeBorder(palette.divider, lineWidth: 1))
                .contentShape(Capsule())
            }
        }
        .accessibilityLabel("Canvas size, \(profile.label)")
        .accessibilityIdentifier("home-size-menu")
    }

    private func sendButton(palette: FentonTheme.Palette) -> some View {
        Button(action: begin) {
            Image(systemName: "arrow.up")
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(canBegin ? palette.surface : palette.tertiaryText)
                .frame(width: 44, height: 44)
                .background(Circle().fill(canBegin ? palette.accent : palette.subtleSurface))
                .overlay(Circle().strokeBorder(canBegin ? Color.clear : palette.divider, lineWidth: 1))
                .shadow(color: palette.accent.opacity(canBegin ? 0.35 : 0), radius: 6, y: 3)
                .contentShape(Circle())
        }
        .buttonStyle(PressScaleStyle())
        .disabled(!canBegin)
        .animation(.easeOut(duration: 0.18), value: canBegin)
        .accessibilityLabel("Begin")
        .accessibilityIdentifier("home-prompt-submit")
    }

    // MARK: - Ideas

    private func ideas(palette: FentonTheme.Palette) -> some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                Button(action: surpriseMe) {
                    Label("Surprise me", systemImage: "dice")
                        .font(MonetType.chip)
                        .foregroundStyle(palette.emphasis)
                        .padding(.horizontal, 13)
                        .padding(.vertical, 9)
                        .background(Capsule().fill(palette.emphasis.opacity(0.1)))
                        .contentShape(Capsule())
                }
                .buttonStyle(PressScaleStyle())
                .disabled(!connected)
                .opacity(connected ? 1 : 0.5)
                .accessibilityIdentifier("home-surprise-me")

                ForEach(Array(PromptIdea.all.enumerated()), id: \.element.id) { index, idea in
                    Button {
                        prompt = idea.text
                    } label: {
                        HStack(spacing: 7) {
                            PaintDabs(colors: idea.dabs)
                            Text(idea.text)
                                .font(.system(.subheadline, design: .serif).italic())
                                .foregroundStyle(palette.secondaryText)
                        }
                        .padding(.horizontal, 13)
                        .padding(.vertical, 8)
                        .background(Capsule().fill(palette.subtleSurface))
                        .contentShape(Capsule())
                    }
                    .buttonStyle(PressScaleStyle())
                    .accessibilityLabel("Idea: \(idea.text)")
                    .accessibilityIdentifier("home-idea-\(index)")
                }
            }
        }
        .scrollIndicators(.hidden)
        .contentMargins(.horizontal, HomeView.gutter, for: .scrollContent)
        .padding(.horizontal, -HomeView.gutter)
    }

    // MARK: - Actions

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

/// A rounded rectangle in a canvas profile's proportions, fit to its frame.
private struct AspectGlyph: Shape {
    let width: Int
    let height: Int

    func path(in rect: CGRect) -> SwiftUI.Path {
        let ratio = CGFloat(width) / CGFloat(max(height, 1))
        let size = ratio >= 1
            ? CGSize(width: rect.width, height: rect.width / ratio)
            : CGSize(width: rect.height * ratio, height: rect.height)
        let frame = CGRect(
            x: rect.midX - size.width / 2, y: rect.midY - size.height / 2, width: size.width, height: size.height
        )
        return SwiftUI.Path(roundedRect: frame.insetBy(dx: 0.6, dy: 0.6), cornerRadius: 2)
    }
}

/// Two small, slightly tilted brush dabs in an idea's colors.
private struct PaintDabs: View {
    let colors: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(colors.enumerated()), id: \.offset) { index, hex in
                UnevenRoundedRectangle(topLeadingRadius: 3, bottomLeadingRadius: 2, bottomTrailingRadius: 3, topTrailingRadius: 1.5)
                    .fill(Color(hex: hex))
                    .frame(width: index == 0 ? 14 : 11, height: 5)
                    .offset(x: CGFloat(index) * 3)
            }
        }
        .rotationEffect(.degrees(-12))
        .accessibilityHidden(true)
    }
}
