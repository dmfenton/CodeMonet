import FentonDesignSystem
import MonetProtocol
import MonetStudio
import SwiftUI

/// Home screen (ux spec §5): the "Start Drawing" card (prompt input, style
/// picker, Surprise Me) plus a conditional Continue/Recent-work section
/// (§5.2, `HomeSelectors.continueCardKind`) and connection hint (§5.3).
/// Reads `AppEnvironment` for navigation/studio state; the New Canvas sheet
/// is a native-improvement entry point (ux spec §7.2's note) reachable from
/// the header here, since no RN control ever opened it.
struct HomeView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme
    @State private var prompt = ""
    @State private var style: DrawingStyleType = .plotter
    @FocusState private var promptFocused: Bool

    var body: some View {
        let state = environment.studio.state
        let palette = theme.palette(for: colorScheme)
        let connected = environment.studio.connected

        ScrollView {
            VStack(alignment: .leading, spacing: FentonSpacing.large) {
                startDrawingSection(connected: connected)

                if HomeSelectors.hasRecentWork(state) {
                    orDivider(palette: palette)
                    continueSection(state: state, connected: connected, palette: palette)
                }

                if !connected {
                    connectionHint(palette: palette)
                }
            }
            .padding(FentonSpacing.medium)
        }
        .scrollBounceBehavior(.basedOnSize)
        .scrollDismissesKeyboard(.interactively)
        .background(
            RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous)
                .fill(palette.elevatedSurface)
        )
        .padding(FentonSpacing.medium)
        .background(palette.surface)
        .accessibilityIdentifier("home-panel")
        .sheet(isPresented: newCanvasPresented) {
            NewCanvasView(initialStyle: style)
        }
    }

    // MARK: - Start Drawing

    @ViewBuilder
    private func startDrawingSection(connected: Bool) -> some View {
        VStack(alignment: .leading, spacing: FentonSpacing.medium) {
            HStack {
                Text("Start Drawing")
                    .font(.system(.body, weight: .semibold))
                Spacer()
                Button {
                    environment.navigation.activeModal = .newCanvas
                } label: {
                    Image(systemName: "slider.horizontal.3")
                        .accessibilityHidden(true)
                }
                .accessibilityLabel("New Canvas options")
                .accessibilityIdentifier("home-new-canvas-button")
            }

            promptInput(connected: connected)

            StylePickerView(label: "Style", selection: $style, variant: .segmented, testIDPrefix: "style")

            surpriseMeButton(connected: connected)
        }
    }

    @ViewBuilder
    private func promptInput(connected: Bool) -> some View {
        let palette = theme.palette(for: colorScheme)
        let canSubmit = HomeSelectors.canSubmit(prompt: prompt, connected: connected)

        HStack(spacing: FentonSpacing.small) {
            TextField("Describe your next piece…", text: $prompt)
                .focused($promptFocused)
                .submitLabel(.go)
                .onSubmit { startWithPrompt() }
                .onChange(of: prompt) { _, newValue in
                    if newValue.count > 200 { prompt = String(newValue.prefix(200)) }
                }
                .accessibilityIdentifier("home-prompt-input")

            Button {
                startWithPrompt()
            } label: {
                Image(systemName: "arrow.forward")
                    .font(.system(size: 16, weight: .semibold))
                    .frame(width: 40, height: 40)
                    .foregroundStyle(canSubmit ? .white : palette.tertiaryText)
                    .background(
                        Circle().fill(canSubmit ? palette.accent : palette.subtleSurface)
                    )
                    .accessibilityHidden(true)
            }
            .buttonStyle(.plain)
            .disabled(!canSubmit)
            .accessibilityLabel("Start drawing")
            .accessibilityIdentifier("home-prompt-submit")
        }
        .padding(.horizontal, FentonSpacing.medium)
        .padding(.vertical, FentonSpacing.extraSmall)
        .background(
            RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous)
                .strokeBorder(palette.divider)
        )
    }

    @ViewBuilder
    private func surpriseMeButton(connected: Bool) -> some View {
        let palette = theme.palette(for: colorScheme)
        Button {
            startSurpriseMe()
        } label: {
            Label("Surprise Me", systemImage: "sparkles")
                .font(.system(.body, weight: .medium))
                .frame(maxWidth: .infinity)
                .padding(.vertical, FentonSpacing.medium)
                .foregroundStyle(palette.text)
                .background(
                    RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous)
                        .fill(palette.subtleSurface)
                )
        }
        .buttonStyle(.plain)
        .disabled(!connected)
        .opacity(connected ? 1 : 0.5)
        .sensoryFeedback(.impact(weight: .light), trigger: connected)
        .accessibilityIdentifier("home-surprise-me")
    }

    // MARK: - Continue section

    @ViewBuilder
    private func orDivider(palette: FentonTheme.Palette) -> some View {
        HStack(spacing: FentonSpacing.medium) {
            Rectangle().fill(palette.divider).frame(height: 1)
            Text("OR")
                .font(FentonTypography.caption.weight(.medium))
                .foregroundStyle(palette.tertiaryText)
            Rectangle().fill(palette.divider).frame(height: 1)
        }
    }

    @ViewBuilder
    private func continueSection(state: StudioState, connected: Bool, palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .leading, spacing: FentonSpacing.small) {
            Text(HomeSelectors.continueSectionHeader(state))
                .font(.system(.body, weight: .semibold))

            ContinueCard(kind: HomeSelectors.continueCardKind(state), connected: connected, onContinue: continueWork)

            Button {
                environment.navigation.openGallery(from: .home)
            } label: {
                HStack(spacing: FentonSpacing.extraSmall) {
                    Image(systemName: "photo.stack")
                        .accessibilityHidden(true)
                    Text(state.gallery.isEmpty ? "View Gallery" : "View Gallery (\(state.gallery.count))")
                }
                .font(FentonTypography.caption.weight(.medium))
                .foregroundStyle(palette.secondaryText)
                .frame(maxWidth: .infinity)
                .padding(.vertical, FentonSpacing.small)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("home-gallery")
        }
    }

    @ViewBuilder
    private func connectionHint(palette: FentonTheme.Palette) -> some View {
        HStack(spacing: FentonSpacing.extraSmall) {
            Image(systemName: "cloud.slash")
                .accessibilityHidden(true)
            Text("Connecting…")
        }
        .font(FentonTypography.caption)
        .foregroundStyle(palette.tertiaryText)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Actions (ux spec §1.1: Home -> Studio transitions)

    private var newCanvasPresented: Binding<Bool> {
        Binding(
            get: { environment.navigation.activeModal == .newCanvas },
            set: { if !$0 { environment.navigation.activeModal = nil } }
        )
    }

    private func startWithPrompt() {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard HomeSelectors.canSubmit(prompt: prompt, connected: environment.studio.connected) else { return }
        prompt = ""
        promptFocused = false
        environment.studio.send(.newCanvas(direction: trimmed, drawingStyle: style, canvasWidth: nil, canvasHeight: nil))
        environment.studio.send(.resume(direction: nil))
        environment.navigation.screen = .studio
    }

    private func startSurpriseMe() {
        environment.studio.send(.newCanvas(direction: nil, drawingStyle: style, canvasWidth: nil, canvasHeight: nil))
        environment.studio.send(.resume(direction: nil))
        environment.navigation.screen = .studio
    }

    private func continueWork() {
        if environment.studio.state.paused {
            environment.studio.send(.resume(direction: nil))
        }
        environment.navigation.screen = .studio
    }
}

/// ux spec §5.2. A pure rendering of `ContinueCardKind` — live work is a
/// tappable card with a WIP preview + "Continue" pill; a completed piece is
/// a static card showing its authenticated thumbnail.
private struct ContinueCard: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    let kind: ContinueCardKind
    let connected: Bool
    let onContinue: () -> Void

    var body: some View {
        switch kind {
        case .none:
            EmptyView()
        case let .live(strokes, canvasWidth, canvasHeight, styleConfig, title):
            Button(action: onContinue) {
                let preview = livePreview(strokes: strokes, canvasWidth: canvasWidth, canvasHeight: canvasHeight, styleConfig: styleConfig)
                content(
                    preview: AnyView(preview),
                    aspectRatio: CGFloat(canvasWidth) / CGFloat(max(canvasHeight, 1)),
                    title: title,
                    showsContinuePill: true
                )
            }
            .buttonStyle(.plain)
            .disabled(!connected)
            .opacity(connected ? 1 : 0.6)
            .accessibilityIdentifier("home-continue-button")
        case let .completed(entry):
            content(
                preview: AnyView(
                    AuthenticatedThumbnailView(
                        token: entry.thumbnailToken,
                        fallbackSymbol: "paintbrush",
                        fallbackText: "Recent drawing"
                    )
                ),
                aspectRatio: CGFloat(entry.width) / CGFloat(max(entry.height, 1)),
                title: entry.title ?? "#\(entry.pieceNumber)",
                showsContinuePill: false
            )
            .accessibilityIdentifier("home-recent-card")
        }
    }

    @ViewBuilder
    private func livePreview(
        strokes: [MonetProtocol.Path], canvasWidth: Int, canvasHeight: Int, styleConfig: DrawingStyleConfig
    ) -> some View {
        if strokes.isEmpty {
            VStack(spacing: FentonSpacing.small) {
                Image(systemName: "paintbrush")
                    .font(.system(size: 28, weight: .light))
                    .accessibilityHidden(true)
                Text("Work in progress")
                    .font(FentonTypography.caption)
            }
            .foregroundStyle(theme.palette(for: colorScheme).tertiaryText)
        } else {
            WipPreview(strokes: strokes, canvasWidth: canvasWidth, canvasHeight: canvasHeight, styleConfig: styleConfig)
        }
    }

    @ViewBuilder
    private func content(preview: AnyView, aspectRatio: CGFloat, title: String, showsContinuePill: Bool) -> some View {
        let palette = theme.palette(for: colorScheme)
        VStack(spacing: 0) {
            preview
                .aspectRatio(aspectRatio.isFinite && aspectRatio > 0 ? aspectRatio : 4.0 / 3.0, contentMode: .fit)
                .frame(maxWidth: .infinity)
                .background(CodeMonetDesignSystem.Extra.canvasBackground)

            HStack {
                Text(title)
                    .font(.system(.body, weight: .semibold))
                    .foregroundStyle(palette.text)
                    .lineLimit(1)
                Spacer()
                if showsContinuePill {
                    HStack(spacing: FentonSpacing.extraSmall) {
                        Text("Continue")
                        Image(systemName: "arrow.forward")
                            .accessibilityHidden(true)
                    }
                    .font(FentonTypography.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, FentonSpacing.medium)
                    .padding(.vertical, FentonSpacing.small)
                    .background(Capsule().fill(palette.accent))
                }
            }
            .padding(FentonSpacing.medium)
        }
        .background(CodeMonetDesignSystem.Extra.canvasBackground)
        .clipShape(RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous)
                .strokeBorder(palette.divider, lineWidth: 1)
        )
    }
}
