import FentonDesignSystem
import MonetProtocol
import MonetStudio
import SwiftUI

/// Home: the brand header, the live piece hung "on the easel" as the hero,
/// one composer ("What should we paint next?") that starts every new piece,
/// and a strip of recent gallery pieces.
struct HomeView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    /// Horizontal page margin; the horizontal strips bleed past it.
    static let gutter: CGFloat = 20
    private static let composerAnchor = "home-composer"

    @State private var composerFocused = false

    var body: some View {
        let state = environment.studio.state
        let palette = theme.palette(for: colorScheme)
        let connected = environment.studio.connected
        let easel = HomeSelectors.easel(state, receivingUpdates: environment.studio.receivingUpdates)

        ScrollViewReader { scroller in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    header
                        .padding(.bottom, 14)

                    if let easel {
                        EaselSection(
                            easel: easel,
                            connected: connected,
                            onContinue: continueWork,
                            onPause: pause
                        )
                        .padding(.bottom, 34)
                    }

                    headline(palette: palette, next: easel != nil)
                        .padding(.bottom, 14)
                        .id(Self.composerAnchor)
                    HomeComposer(
                        connected: connected,
                        replacesEasel: easel != nil,
                        onFocusChange: { focused in
                            composerFocused = focused
                            if focused { liftComposer(scroller) }
                        },
                        onStarted: { environment.navigation.screen = .studio }
                    )

                    recentSection(state: state, palette: palette)
                        .padding(.top, 34)

                    if !connected {
                        connectionHint(palette: palette)
                    }
                }
                .padding(.horizontal, Self.gutter)
                .padding(.top, FentonSpacing.small)
                .padding(.bottom, 48)
                .frame(maxWidth: 560)
                .frame(maxWidth: .infinity)
            }
            .scrollBounceBehavior(.basedOnSize)
            .scrollDismissesKeyboard(.interactively)
            // Scrolling at focus can be clamped before the keyboard inset
            // lands (short screens); scroll again once it has.
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardDidShowNotification)) { _ in
                if composerFocused { liftComposer(scroller) }
            }
        }
        .overlay(alignment: .bottom) {
            bottomFade(palette: palette).opacity(composerFocused ? 0 : 1)
        }
        .background {
            ZStack {
                palette.surface
                PaperGrain()
            }
            .ignoresSafeArea()
        }
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

    /// "What should we paint next?" — the last word set in italic accent.
    private func headline(palette: FentonTheme.Palette, next: Bool) -> some View {
        (Text("What should we paint ")
            + Text(next ? "next?" : "today?").italic().foregroundStyle(palette.accent))
            .font(MonetType.hero)
            .foregroundStyle(palette.text)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
    }

    @ViewBuilder
    private func recentSection(state: StudioState, palette: FentonTheme.Palette) -> some View {
        let recent = HomeSelectors.recentPieces(state)
        VStack(alignment: .leading, spacing: 14) {
            RuleLabel("From the gallery") {
                Button {
                    environment.navigation.openGallery(from: .home)
                } label: {
                    HStack(spacing: 3) {
                        Text("See all")
                        if !state.gallery.isEmpty {
                            Text("\(state.gallery.count)")
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
                ScrollView(.horizontal) {
                    HStack(alignment: .top, spacing: 14) {
                        ForEach(recent) { entry in
                            RecentCard(entry: entry) {
                                environment.navigation.openGallery(from: .home, focusing: entry.pieceNumber)
                            }
                        }
                    }
                }
                .scrollIndicators(.hidden)
                .contentMargins(.horizontal, Self.gutter, for: .scrollContent)
                .padding(.horizontal, -Self.gutter)
            }
        }
    }

    /// Content dissolves into the paper at the bottom edge instead of being
    /// cut off under the home indicator.
    private func bottomFade(palette: FentonTheme.Palette) -> some View {
        LinearGradient(
            stops: [
                .init(color: palette.surface.opacity(0), location: 0),
                .init(color: palette.surface.opacity(0.85), location: 0.6),
                .init(color: palette.surface, location: 1),
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .frame(height: 56)
        .ignoresSafeArea(edges: .bottom)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
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

    /// The hero pushes the composer below the keyboard; bring the whole
    /// card (and its send button) into view.
    private func liftComposer(_ scroller: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.3)) {
            scroller.scrollTo(Self.composerAnchor, anchor: .top)
        }
    }

    private func continueWork() {
        if environment.studio.state.paused {
            environment.studio.setPausedLocally(false)
            environment.studio.send(.resume(direction: nil))
        }
        environment.navigation.screen = .studio
    }

    private func pause() {
        environment.studio.setPausedLocally(true)
        environment.studio.send(.pause)
    }
}

/// A gallery strip card: the piece in a light mat, its title and date.
private struct RecentCard: View {
    let entry: GalleryEntry
    let onOpen: () -> Void

    static let width: CGFloat = 168

    var body: some View {
        PaletteReader { palette in
            Button(action: onOpen) {
                VStack(alignment: .leading, spacing: 0) {
                    AuthenticatedThumbnailView(token: entry.thumbnailToken, fallbackSymbol: "photo", contentMode: .fill)
                        .frame(width: Self.width - 12, height: (Self.width - 12) * 3 / 4)
                        .clipped()
                        .paperMat(padding: 6)
                        .shadow(color: Color.black.opacity(0.08), radius: 6, y: 4)
                    Text(GalleryFormatting.title(for: entry))
                        .font(MonetType.pieceTitleSmall)
                        .foregroundStyle(palette.text)
                        .lineLimit(1)
                        .padding(.top, 10)
                    Text(GalleryFormatting.shortDate(entry.createdAt).lowercased())
                        .font(MonetType.meta)
                        .foregroundStyle(palette.tertiaryText)
                        .padding(.top, 2)
                }
                .frame(width: Self.width, alignment: .leading)
            }
            .buttonStyle(PressScaleStyle())
            .accessibilityLabel(GalleryFormatting.title(for: entry))
            .accessibilityIdentifier("home-recent-\(entry.pieceNumber)")
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
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(palette.secondaryText)
                    .frame(width: 34, height: 34)
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
