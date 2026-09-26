import FentonDesignSystem
import MonetProtocol
import MonetRender
import MonetStudio
import SwiftUI

/// One saved piece: the large image, title, "date · style · N versions · M
/// strokes", the prompt, a version-by-version replay, and the program that
/// painted it. Pieces saved before version history show the final image only.
struct GalleryPieceDetailView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    let entry: GalleryEntry

    @State private var detail: GalleryPieceStrokes?
    @State private var replayIndex: Int?
    @State private var isPlaying = false
    @State private var replay = PaintingRevealController()
    @State private var showsProgram = false

    private var versions: [PaintingVersionSummary] { detail?.versions ?? [] }
    private var apiBase: String { environment.config.apiBaseURL.absoluteString }

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                topBar(palette: palette)
                if horizontalSizeClass == .regular {
                    HStack(alignment: .top, spacing: 28) {
                        artwork.frame(maxWidth: .infinity)
                        info(palette: palette).frame(width: 320)
                    }
                } else {
                    artwork
                    info(palette: palette).padding(.top, 18)
                }
            }
            .padding(.horizontal, 18)
            .padding(.bottom, FentonSpacing.large)
            .frame(maxWidth: 1000)
            .frame(maxWidth: .infinity)
        }
        .background(palette.surface.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .task(id: entry.pieceNumber) { await load() }
        .sheet(isPresented: $showsProgram) {
            if let summary = programVersion {
                ProgramSheet(
                    title: "\(title) · v\(summary.version)",
                    urlString: PaintingAssetURL.apiAssetUrl(apiBase, summary.assetBase + "painting.py")
                )
            }
        }
    }

    // MARK: - Sections

    private func topBar(palette: FentonTheme.Palette) -> some View {
        HStack {
            Button { dismiss() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(palette.secondaryText)
                    .frame(width: 32, height: 32, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel("Gallery")
            .accessibilityIdentifier("piece-back-button")
            Spacer()
        }
        .padding(.vertical, FentonSpacing.small)
    }

    private var artwork: some View {
        VStack(alignment: .leading, spacing: 12) {
            image
                .aspectRatio(aspectRatio, contentMode: .fit)
                .frame(maxWidth: .infinity)
                .paperMat(padding: 10)
                .accessibilityIdentifier("piece-image")
            if !versions.isEmpty {
                ReplayScrubber(
                    versionCount: versions.count,
                    selectedIndex: replayIndex,
                    isPlaying: isPlaying,
                    onSelect: { index in
                        isPlaying = false
                        replayIndex = index
                    },
                    onTogglePlay: togglePlay
                )
            }
        }
    }

    @ViewBuilder
    private var image: some View {
        if let replayIndex, versions.indices.contains(replayIndex) {
            ReplayCanvas(
                controller: replay,
                base: isPlaying ? (replayIndex > 0 ? ref(at: replayIndex - 1) : nil) : ref(at: replayIndex),
                playing: isPlaying ? ref(at: replayIndex) : nil,
                apiBaseURL: environment.config.apiBaseURL,
                onPlaybackDone: advanceReplay
            )
        } else if let url = PaintingAssetURL.galleryRasterImageUrl(
            apiBase: apiBase, format: detail?.format ?? entry.format, imageURL: detail?.imageURL
        ) {
            GalleryRasterImageView(urlString: url)
        } else if let detail, !detail.strokes.isEmpty {
            WipPreview(
                strokes: detail.strokes,
                canvasWidth: detail.canvasWidth,
                canvasHeight: detail.canvasHeight,
                styleConfig: detail.styleConfig ?? (detail.drawingStyle == .paint ? .paint : .plotter)
            )
        } else {
            AuthenticatedThumbnailView(token: entry.thumbnailToken, fallbackSymbol: "photo", contentMode: .fit)
        }
    }

    private func info(palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title)
                .font(Font.system(.title, design: .serif))
                .foregroundStyle(palette.text)
                .accessibilityIdentifier("piece-title")
            Text(GalleryFormatting.detailMetaLine(
                createdAt: entry.createdAt,
                style: detail?.drawingStyle ?? entry.drawingStyle,
                versionCount: versions.count,
                strokeCount: detail?.strokeCount ?? entry.strokeCount
            ))
            .font(MonetType.meta)
            .foregroundStyle(palette.tertiaryText)
            .padding(.top, 6)

            if let prompt = detail?.prompt?.trimmingCharacters(in: .whitespacesAndNewlines), !prompt.isEmpty {
                SectionLabel("prompt").padding(.top, FentonSpacing.medium)
                Text("“\(prompt)”")
                    .font(Font.system(.body, design: .serif).italic())
                    .foregroundStyle(palette.secondaryText)
                    .padding(.top, 3)
                    .accessibilityIdentifier("piece-prompt")
            }

            actions(palette: palette).padding(.top, FentonSpacing.medium)
        }
    }

    private func actions(palette: FentonTheme.Palette) -> some View {
        HStack(spacing: 8) {
            if !versions.isEmpty {
                Button { showsProgram = true } label: {
                    ChipLabel(text: "View program", systemImage: "chevron.left.forwardslash.chevron.right")
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("piece-view-program")
            }
            Button(action: openInStudio) {
                ChipLabel(text: "Open in studio", systemImage: "rectangle.on.rectangle")
            }
            .buttonStyle(.plain)
            .disabled(detail == nil)
            .accessibilityIdentifier("piece-open-in-studio")
        }
    }

    // MARK: - Derived

    private var title: String {
        PieceTitle.resolve(title: detail?.title ?? entry.title, prompt: detail?.prompt, pieceNumber: entry.pieceNumber)
    }

    private var aspectRatio: CGFloat {
        let width = detail?.canvasWidth ?? entry.width
        let height = detail?.canvasHeight ?? entry.height
        return CGFloat(width) / CGFloat(max(height, 1))
    }

    /// The program shown: the version on screen in the replay, else the last.
    private var programVersion: PaintingVersionSummary? {
        if let replayIndex, versions.indices.contains(replayIndex) { return versions[replayIndex] }
        return versions.last
    }

    private func ref(at index: Int) -> PaintingVersionRef {
        versions[index].ref(pieceNumber: entry.pieceNumber)
    }

    // MARK: - Actions

    private func load() async {
        detail = try? await environment.restClient.galleryPieceStrokes(pieceNumber: entry.pieceNumber)
    }

    private func togglePlay() {
        if isPlaying {
            isPlaying = false
            return
        }
        if replayIndex == nil || replayIndex == versions.count - 1 { replayIndex = 0 }
        isPlaying = true
    }

    /// Called from the reveal loop when a version finishes; deferred so the
    /// state change lands outside the render pass that reported it.
    private func advanceReplay(_ assetBase: String) {
        Task { @MainActor in
            guard isPlaying, let index = replayIndex, versions.indices.contains(index),
                  versions[index].assetBase == assetBase else { return }
            if index + 1 < versions.count {
                replayIndex = index + 1
            } else {
                isPlaying = false
            }
        }
    }

    /// Opens the piece view-only in the studio (the pre-redesign tap action).
    private func openInStudio() {
        guard let detail else { return }
        environment.studio.applyLoadedGalleryPiece(detail)
        environment.navigation.screen = .studio
    }
}

/// Drives a `PaintingRevealController` for the replay: static final image
/// when `playing` is nil, the version's stroke-by-stroke reveal otherwise.
private struct ReplayCanvas: View {
    let controller: PaintingRevealController
    let base: PaintingVersionRef?
    let playing: PaintingVersionRef?
    let apiBaseURL: URL
    let onPlaybackDone: (String) -> Void

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60.0, paused: playing == nil)) { timeline in
            if let image = controller.frame(
                base: base, playing: playing, apiBaseURL: apiBaseURL, now: timeline.date, onPlaybackDone: onPlaybackDone
            ) {
                Image(decorative: image, scale: 1).resizable()
            } else {
                CodeMonetDesignSystem.Extra.canvasBackground
            }
        }
    }
}
