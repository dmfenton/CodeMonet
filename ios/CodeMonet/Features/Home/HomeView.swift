import FentonDesignSystem
import MonetProtocol
import MonetRender
import MonetStudio
import SwiftUI

/// Home: the brand header, the live piece "on the easel", one composer
/// ("What should we paint today?") that starts every new piece, and the
/// three most recent gallery pieces.
struct HomeView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    var body: some View {
        let state = environment.studio.state
        let palette = theme.palette(for: colorScheme)
        let connected = environment.studio.connected

        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header
                    .padding(.bottom, FentonSpacing.medium)

                if let easel = HomeSelectors.easel(state) {
                    EaselRow(easel: easel, connected: connected, onContinue: continueWork)
                    Rectangle().fill(palette.divider).frame(height: 1)
                        .padding(.vertical, FentonSpacing.large - 4)
                }

                Text("What should we paint today?")
                    .font(MonetType.display)
                    .foregroundStyle(palette.text)
                    .padding(.bottom, FentonSpacing.small + 4)
                HomeComposer(connected: connected, onStarted: { environment.navigation.screen = .studio })

                recentSection(state: state, palette: palette)

                if !connected {
                    connectionHint(palette: palette)
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, FentonSpacing.small)
            .padding(.bottom, FentonSpacing.large)
            .frame(maxWidth: 560)
            .frame(maxWidth: .infinity)
        }
        .scrollBounceBehavior(.basedOnSize)
        .scrollDismissesKeyboard(.interactively)
        .background(palette.surface.ignoresSafeArea())
        .accessibilityIdentifier("home-panel")
    }

    private var header: some View {
        HStack {
            BrandLockup(markSize: 28, wordSize: 20)
            Spacer()
            AccountMenu()
        }
        .padding(.top, FentonSpacing.small)
    }

    @ViewBuilder
    private func recentSection(state: StudioState, palette: FentonTheme.Palette) -> some View {
        let recent = HomeSelectors.recentPieces(state)
        VStack(alignment: .leading, spacing: FentonSpacing.small) {
            HStack(alignment: .firstTextBaseline) {
                SectionLabel("recent")
                Spacer()
                Button {
                    environment.navigation.openGallery(from: .home)
                } label: {
                    HStack(spacing: 3) {
                        Text("Gallery")
                        if !state.gallery.isEmpty {
                            Text("\(state.gallery.count)")
                                .font(MonetType.meta)
                                .foregroundStyle(palette.tertiaryText)
                        }
                        Image(systemName: "chevron.forward")
                            .imageScale(.small)
                            .accessibilityHidden(true)
                    }
                    .font(MonetType.chip)
                    .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("home-gallery")
            }
            if recent.isEmpty {
                Text("Finished pieces land here.")
                    .font(MonetType.proseItalic)
                    .foregroundStyle(palette.tertiaryText)
            } else {
                HStack(alignment: .top, spacing: FentonSpacing.small) {
                    ForEach(recent) { entry in
                        Button {
                            environment.navigation.openGallery(from: .home, focusing: entry.pieceNumber)
                        } label: {
                            AuthenticatedThumbnailView(token: entry.thumbnailToken, fallbackSymbol: "photo", contentMode: .fill)
                                .aspectRatio(4.0 / 3.0, contentMode: .fit)
                                .clipped()
                                .paperMat(padding: 4)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(GalleryFormatting.title(for: entry))
                        .accessibilityIdentifier("home-recent-\(entry.pieceNumber)")
                    }
                    ForEach(recent.count ..< HomeSelectors.recentLimit, id: \.self) { _ in
                        Color.clear.frame(maxWidth: .infinity)
                    }
                }
            }
        }
        .padding(.top, FentonSpacing.large)
    }

    private func connectionHint(palette: FentonTheme.Palette) -> some View {
        HStack(spacing: FentonSpacing.extraSmall) {
            ProgressView()
                .controlSize(.mini)
                .tint(palette.tertiaryText)
            Text("connecting to the studio…")
        }
        .font(MonetType.meta)
        .foregroundStyle(palette.tertiaryText)
        .frame(maxWidth: .infinity)
        .padding(.top, FentonSpacing.large)
        .accessibilityIdentifier("home-connecting")
    }

    private func continueWork() {
        if environment.studio.state.paused {
            environment.studio.setPausedLocally(false)
            environment.studio.send(.resume(direction: nil))
        }
        environment.navigation.screen = .studio
    }
}

/// "On the easel": the live piece's thumbnail in a mat, its title, a
/// monospaced status line, and Watch/Continue.
private struct EaselRow: View {
    @Environment(AppEnvironment.self) private var environment
    let easel: EaselModel
    let connected: Bool
    let onContinue: () -> Void

    var body: some View {
        PaletteReader { palette in
            VStack(alignment: .leading, spacing: FentonSpacing.small) {
                SectionLabel("on the easel")
                HStack(alignment: .center, spacing: 14) {
                    preview
                        .aspectRatio(CGFloat(easel.canvasWidth) / CGFloat(max(easel.canvasHeight, 1)), contentMode: .fit)
                        .frame(width: 120)
                        .paperMat()
                    VStack(alignment: .leading, spacing: 6) {
                        Text(easel.title)
                            .font(MonetType.pieceTitle)
                            .foregroundStyle(palette.text)
                            .lineLimit(2)
                        HStack(spacing: 5) {
                            Circle()
                                .fill(easel.isActive ? palette.emphasis : palette.tertiaryText)
                                .frame(width: 6, height: 6)
                            Text(easel.statusLine)
                                .font(MonetType.meta)
                                .foregroundStyle(palette.tertiaryText)
                                .lineLimit(1)
                        }
                        Button(action: onContinue) {
                            HStack(spacing: 4) {
                                Text(easel.isActive ? "Watch" : "Continue")
                                Image(systemName: "arrow.right").accessibilityHidden(true)
                            }
                        }
                        .buttonStyle(PrimaryCapsuleStyle(compact: true))
                        .disabled(!connected)
                        .padding(.top, 2)
                        .accessibilityIdentifier("home-continue-button")
                    }
                    Spacer(minLength: 0)
                }
            }
        }
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
        case .blank:
            CodeMonetDesignSystem.Extra.canvasBackground
        }
    }
}

/// The signed-in account: initials avatar with the email and Sign out.
private struct AccountMenu: View {
    @Environment(AppEnvironment.self) private var environment

    private var email: String? {
        if case let .signedIn(user) = environment.auth.state { return user.email }
        return nil
    }

    var body: some View {
        PaletteReader { palette in
            Menu {
                if let email {
                    Text(email)
                }
                Button("Sign out", systemImage: "rectangle.portrait.and.arrow.right", role: .destructive) {
                    Task { await environment.auth.signOut() }
                }
            } label: {
                Text(Self.initials(email))
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(palette.secondaryText)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(palette.subtleSurface))
                    .overlay(Circle().strokeBorder(palette.divider, lineWidth: 1))
            }
            .accessibilityLabel("Account")
            .accessibilityIdentifier("home-account-menu")
        }
    }

    static func initials(_ email: String?) -> String {
        guard let name = email?.split(separator: "@").first, !name.isEmpty else { return "·" }
        let parts = name.split(whereSeparator: { ".-_+".contains($0) }).prefix(2)
        return parts.compactMap(\.first).map { String($0).uppercased() }.joined()
    }
}
