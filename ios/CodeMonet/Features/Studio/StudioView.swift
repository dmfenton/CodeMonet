import FentonDesignSystem
import MonetProtocol
import MonetRender
import MonetStudio
import SwiftUI

private extension View {
    func frame(size: CGSize) -> some View {
        frame(width: size.width, height: size.height)
    }
}

/// Studio: top bar (back, title, status, menu), the canvas in a paper mat,
/// the stage bar and version chips (paint mode), the notebook, and the
/// always-visible nudge bar with pause/resume. On regular width the notebook
/// sits beside the canvas.
///
/// View-only mode (`state.viewingPiece != nil`, a gallery piece opened in
/// the studio) hides the notebook, nudge bar, and version controls.
struct StudioView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    /// View-local "Draw on canvas" toggle — see `CanvasView.drawingEnabled`.
    @State private var drawingEnabled = false
    @State private var painting = PaintingRevealController()
    /// An older version chosen from the version chips, shown over the live canvas.
    @State private var pinnedVersion: Int?
    @State private var pieceCompleteHapticTrigger = false
    @State private var pauseHapticTrigger = false

    private var state: StudioState { environment.studio.state }
    private var isViewOnly: Bool { state.viewingPiece != nil }
    private var apiBaseURL: URL { environment.config.apiBaseURL }

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        VStack(spacing: 0) {
            StudioTopBar(
                title: title,
                pill: StudioPresentation.statusPill(for: state),
                menu: StudioMenuState(
                    paused: state.paused,
                    viewOnly: isViewOnly,
                    drawingEnabled: drawingEnabled,
                    connected: environment.studio.connected,
                    galleryCount: state.gallery.count
                ),
                onBack: goHome,
                onAction: handle
            )
            if horizontalSizeClass == .regular {
                HStack(alignment: .top, spacing: 20) {
                    GeometryReader { proxy in
                        // A finite cap: `.infinity` would make the canvas frame
                        // greedy and float the canvas mid-column.
                        canvasColumn(width: proxy.size.width, maxCanvasHeight: proxy.size.height * 0.72)
                    }
                    .padding(.leading, 20)
                    if !isViewOnly {
                        VStack(spacing: 0) {
                            notebook
                            nudgeBar
                        }
                        .frame(width: 360)
                        .background(palette.elevatedSurface)
                        .overlay(alignment: .leading) { Rectangle().fill(palette.divider).frame(width: 1) }
                    }
                }
            } else {
                GeometryReader { proxy in
                    VStack(spacing: 0) {
                        canvasColumn(width: proxy.size.width - 28, maxCanvasHeight: proxy.size.height * (isViewOnly ? 0.9 : 0.46))
                            .padding(.horizontal, 14)
                        if isViewOnly {
                            Spacer(minLength: 0)
                        } else {
                            notebook
                            nudgeBar
                        }
                    }
                }
            }
        }
        .background(palette.surface.ignoresSafeArea())
        .onAppear { environment.studio.startPlayback() }
        .onDisappear { environment.studio.stopPlayback() }
        .onChange(of: state.pieceNumber) { pinnedVersion = nil }
        .onChange(of: state.messages.last?.id) {
            guard state.messages.last?.type == .pieceComplete else { return }
            pieceCompleteHapticTrigger.toggle()
        }
        .sensoryFeedback(.success, trigger: pieceCompleteHapticTrigger)
        .sensoryFeedback(.selection, trigger: pauseHapticTrigger)
        .sensoryFeedback(.selection, trigger: drawingEnabled)
        .sensoryFeedback(.selection, trigger: pinnedVersion)
    }

    // MARK: - Canvas column

    private func canvasColumn(width: CGFloat, maxCanvasHeight: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            CanvasView(drawingEnabled: drawingEnabled, paintingController: painting, pinnedImageURL: pinnedImageURL)
                .frame(size: canvasSize(width: width, maxHeight: maxCanvasHeight))
                .paperMat(padding: Self.matPadding)
                .frame(maxWidth: .infinity)
                .animation(.easeInOut(duration: 0.2), value: pinnedVersion)
            if showsVersionControls {
                if let segments = stageSegments {
                    StageBarView(segments: segments)
                }
                VersionChipsView(
                    versions: state.versions,
                    liveVersion: liveRef?.version,
                    pinnedVersion: validPinnedVersion,
                    onSelect: { pinnedVersion = $0 }
                )
            }
        }
        .padding(.top, 4)
        .padding(.bottom, 6)
        .task(id: displayedRef?.assetBase) {
            guard let ref = displayedRef else { return }
            await painting.loadManifest(for: ref, apiBaseURL: apiBaseURL)
        }
    }

    private static let matPadding: CGFloat = 8

    /// The canvas's exact on-screen size: full width at its aspect ratio,
    /// shrunk to fit `maxHeight` (mat included) for tall canvases.
    private func canvasSize(width: CGFloat, maxHeight: CGFloat) -> CGSize {
        let aspect = CGFloat(state.canvasWidth) / CGFloat(max(state.canvasHeight, 1))
        let inset = Self.matPadding * 2
        var size = CGSize(width: max(width - inset, 1), height: max(width - inset, 1) / aspect)
        if size.height > maxHeight - inset {
            size.height = max(maxHeight - inset, 1)
            size.width = size.height * aspect
        }
        return size
    }

    private var showsVersionControls: Bool {
        !isViewOnly && !state.versions.isEmpty
    }

    /// The version currently on the canvas, live (revealing or settled).
    private var liveRef: PaintingVersionRef? {
        state.painting.playing ?? state.painting.base
    }

    private var validPinnedVersion: Int? {
        guard let pinnedVersion, pinnedVersion != liveRef?.version,
              state.versions.contains(where: { $0.version == pinnedVersion }) else { return nil }
        return pinnedVersion
    }

    /// The version whose stages the bar shows: the pinned one, else live.
    private var displayedRef: PaintingVersionRef? {
        if let pinned = validPinnedVersion, let summary = state.versions.first(where: { $0.version == pinned }) {
            return summary.ref(pieceNumber: state.pieceNumber)
        }
        return liveRef
    }

    private var pinnedImageURL: String? {
        guard validPinnedVersion != nil, let ref = displayedRef else { return nil }
        return PaintingAssetURL.paintingAssetUrl(apiBase: apiBaseURL.absoluteString, ref: ref, file: "final.png")
    }

    private var stageSegments: [StageSegment]? {
        guard let ref = displayedRef, let manifest = painting.manifests[ref.assetBase], !manifest.keyframes.isEmpty else {
            return nil
        }
        // Only a playing (not yet settled) live version has stages still to come.
        var revealing: Int?
        if validPinnedVersion == nil, state.painting.playing?.assetBase == ref.assetBase {
            let marker = painting.revealing
            revealing = marker?.assetBase == ref.assetBase ? marker?.keyframe : 0
        }
        return StageBar.segments(manifest: manifest, revealingKeyframe: revealing)
    }

    // MARK: - Notebook + nudge bar

    private var notebook: some View {
        NotebookView(
            entries: Notebook.entries(state),
            showsVersions: state.drawingStyle == .paint || !state.versions.isEmpty,
            strokes: strokeCount(forVersion:),
            requestStrokes: { version in
                guard let summary = state.versions.first(where: { $0.version == version }) else { return }
                Task { await painting.loadManifest(for: summary.ref(pieceNumber: state.pieceNumber), apiBaseURL: apiBaseURL) }
            }
        )
        .frame(maxHeight: .infinity)
    }

    private func strokeCount(forVersion version: Int) -> Int? {
        guard let summary = state.versions.first(where: { $0.version == version }) else { return nil }
        return summary.ops ?? painting.manifests[summary.assetBase]?.strokeOpCount
    }

    private var nudgeBar: some View {
        NudgeBar(
            paused: state.paused,
            connected: environment.studio.connected,
            onTogglePause: togglePause,
            onSend: { environment.studio.sendNudge($0) }
        )
    }

    // MARK: - Title

    private var title: String {
        if let viewing = state.viewingPiece {
            let entry = state.gallery.first { $0.pieceNumber == viewing }
            return PieceTitle.resolve(title: entry?.title, prompt: nil, pieceNumber: viewing)
        }
        return PieceTitle.resolve(title: state.title, prompt: state.prompt, pieceNumber: state.pieceNumber)
    }

    // MARK: - Actions

    private func handle(_ action: StudioMenuAction) {
        switch action {
        case .newPiece:
            goHome()
        case .gallery:
            environment.navigation.openGallery(from: .studio)
        case .toggleDrawing:
            drawingEnabled.toggle()
        case .togglePause:
            togglePause()
        }
    }

    private func togglePause() {
        pauseHapticTrigger.toggle()
        if state.paused {
            environment.studio.setPausedLocally(false)
            environment.studio.send(.resume(direction: nil))
        } else {
            drawingEnabled = false
            environment.studio.setPausedLocally(true)
            environment.studio.send(.pause)
        }
    }

    /// Leaving the studio pauses the painter and restores the live canvas
    /// if a gallery piece was being viewed (ux spec §1.1).
    private func goHome() {
        if !state.paused {
            environment.studio.setPausedLocally(true)
            environment.studio.send(.pause)
        }
        drawingEnabled = false
        environment.studio.clearViewing()
        environment.navigation.screen = .home
    }
}
