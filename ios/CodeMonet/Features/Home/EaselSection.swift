import FentonDesignSystem
import MonetProtocol
import MonetRender
import SwiftUI

/// "On the easel": the live piece hung in a museum mat with a glass status
/// badge, then a placard — title, version detail, and Watch/pause (active)
/// or a full-width Continue (paused).
struct EaselSection: View {
    @Environment(AppEnvironment.self) private var environment
    let easel: EaselModel
    let connected: Bool
    let onContinue: () -> Void
    let onPause: () -> Void

    var body: some View {
        PaletteReader { palette in
            VStack(alignment: .leading, spacing: 0) {
                RuleLabel("On the easel") {
                    Text(Date.now.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day()).lowercased())
                        .font(MonetType.meta)
                        .foregroundStyle(palette.tertiaryText)
                }
                .padding(.bottom, 14)

                Button(action: onContinue) {
                    preview
                        .aspectRatio(CGFloat(easel.canvasWidth) / CGFloat(max(easel.canvasHeight, 1)), contentMode: .fit)
                        .overlay(alignment: .topLeading) { statusBadge.padding(10) }
                        .museumMat()
                        .frame(maxHeight: 460)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(PressScaleStyle())
                .disabled(!connected)
                .accessibilityLabel("\(easel.title), \(easel.status)")
                .accessibilityHint(easel.isActive ? "Watch the painting" : "Continue painting")
                .accessibilityIdentifier("home-easel")

                placard(palette: palette)
                    .padding(.top, 18)
            }
        }
    }

    private func placard(palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(easel.title)
                .font(MonetType.heroTitle)
                .foregroundStyle(palette.text)
                .lineLimit(2)
            if easel.isActive {
                HStack(alignment: .center) {
                    detail(palette: palette)
                    Spacer(minLength: 12)
                    Button(action: onPause) {
                        CircleIconLabel(systemImage: "pause.fill", size: 40)
                            .opacity(connected ? 1 : 0.45)
                    }
                    .buttonStyle(PressScaleStyle())
                    .disabled(!connected)
                    .accessibilityLabel("Pause")
                    .accessibilityIdentifier("home-pause-button")
                    continueButton(title: "Watch", fullWidth: false)
                }
                .padding(.top, 8)
            } else {
                detail(palette: palette)
                    .padding(.top, 6)
                continueButton(title: "Continue painting", fullWidth: true)
                    .padding(.top, 16)
            }
        }
    }

    private func detail(palette: FentonTheme.Palette) -> some View {
        Text(easel.detail)
            .font(MonetType.meta)
            .foregroundStyle(palette.tertiaryText)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func continueButton(title: String, fullWidth: Bool) -> some View {
        Button(action: onContinue) {
            HStack(spacing: 6) {
                Text(title)
                Image(systemName: "arrow.right").accessibilityHidden(true)
            }
            .frame(maxWidth: fullWidth ? .infinity : nil)
        }
        .buttonStyle(PrimaryCapsuleStyle())
        .disabled(!connected)
        .accessibilityIdentifier("home-continue-button")
    }

    /// A frosted capsule on the painting: live dot + status word.
    private var statusBadge: some View {
        HStack(spacing: 6) {
            LiveDot(active: easel.isActive)
            Text(easel.status)
                .font(MonetType.meta)
                .foregroundStyle(CodeMonetDesignSystem.Extra.strokeInk)
        }
        .padding(.leading, 8)
        .padding(.trailing, 10)
        .padding(.vertical, 5)
        .background(Capsule().fill(CodeMonetDesignSystem.Extra.canvasBackground.opacity(0.72)))
        .background(Capsule().fill(.ultraThinMaterial))
        .environment(\.colorScheme, .light)
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private var preview: some View {
        switch easel.preview {
        case let .painting(ref):
            GalleryRasterImageView(
                urlString: PaintingAssetURL.paintingAssetUrl(
                    apiBase: environment.config.apiBaseURL.absoluteString, ref: ref, file: "preview.jpg"
                )
            )
        case let .strokes(strokes, styleConfig):
            WipPreview(strokes: strokes, canvasWidth: easel.canvasWidth, canvasHeight: easel.canvasHeight, styleConfig: styleConfig)
                .background(CodeMonetDesignSystem.Extra.canvasBackground)
        case .blank:
            BlankCanvas()
        }
    }
}

/// The status dot; while the agent works it breathes with a soft halo.
private struct LiveDot: View {
    let active: Bool
    @State private var breathing = false

    var body: some View {
        let ink = CodeMonetDesignSystem.theme.light
        Circle()
            .fill(active ? ink.emphasis : ink.tertiaryText)
            .frame(width: 7, height: 7)
            .background {
                if active {
                    Circle()
                        .fill(ink.emphasis.opacity(0.25))
                        .scaleEffect(breathing ? 2.4 : 1.4)
                        .opacity(breathing ? 0 : 1)
                }
            }
            .onAppear { breathing = active }
            .onChange(of: active) { _, isActive in breathing = isActive }
            .animation(active ? .easeOut(duration: 1.6).repeatForever(autoreverses: false) : .default, value: breathing)
    }
}

/// A started piece with nothing on it yet: bare paper, quietly labeled.
private struct BlankCanvas: View {
    var body: some View {
        ZStack {
            CodeMonetDesignSystem.Extra.canvasBackground
            VStack(spacing: 6) {
                Image(systemName: "paintbrush.pointed")
                    .font(.system(size: 18, weight: .light))
                    .accessibilityHidden(true)
                Text("a blank canvas")
                    .font(MonetType.proseItalic)
            }
            .foregroundStyle(CodeMonetDesignSystem.theme.light.tertiaryText)
        }
    }
}
