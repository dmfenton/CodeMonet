import MonetNetworking
import MonetProtocol
import MonetRender
import MonetStudio
import SwiftUI

/// Hosts `MonetRender.CanvasRenderer` inside SwiftUI (ux spec §6.2): commit
/// strokes, the human's in-progress stroke, the agent's in-progress stroke,
/// a pen-position indicator, idle particles, and the drag gesture that
/// streams human touch points into `StudioStore`.
///
/// Rendering itself is entirely delegated to the frozen `CanvasRenderer`
/// contract (ARCHITECTURE.md, MonetRender package) — this view's only job is
/// assembling `(strokes, styleConfig, size)` inputs (including synthesizing
/// `Path` values for the two in-progress strokes so they render through the
/// same pipeline as committed ones) and driving that call once per frame via
/// `TimelineView`, in step with `StudioStore`'s `PerformerEngine` tick loop
/// (ARCHITECTURE.md's data-flow diagram).
struct CanvasView: View {
    /// Whether the user has toggled the ActionBar's "Draw" button on.
    /// `StudioState` models this field, but `StudioStore` does not yet
    /// expose a way to mutate it (no public `toggleDrawing()`), and nothing
    /// outside Studio UI reads it (it has no wire message — protocol-state
    /// spec's `StudioEvent.toggleDrawing` is client-local only), so
    /// `StudioView` owns it as view state and passes it straight through
    /// rather than reading `environment.studio.state.drawingEnabled`.
    let drawingEnabled: Bool

    @Environment(AppEnvironment.self) private var environment
    @State private var canvasCache = IncrementalCanvasCache()
    /// Drives the raster layer for paint-mode pieces (program-painting spec
    /// §4) — a piece with a live/base `painting_version` has no vector
    /// `Path` strokes to draw, so `frame(state:canvasSize:)` renders this
    /// layer instead of `canvasCache`'s whenever `hasPainting` is true.
    @State private var paintingController = PaintingRevealController()

    @State private var isDragging = false

    var body: some View {
        let state = environment.studio.state
        let canvasSize = CGSize(width: state.canvasWidth, height: state.canvasHeight)
        let viewOnly = state.viewingPiece != nil
        let gestureEnabled = drawingEnabled && !viewOnly

        GeometryReader { proxy in
            let containerSize = CGSize(width: proxy.size.width, height: proxy.size.width * canvasSize.height / max(canvasSize.width, 1))

            ZStack(alignment: .topLeading) {
                if let imagePath = state.viewingImageURL {
                    // A `.raster` gallery piece (program-painting spec §2.1's
                    // `galleryRasterImageUrl`): a static final image, no
                    // reveal animation, no vector strokes at all — entirely
                    // separate from the live-painting/strokes machinery
                    // below.
                    GalleryRasterImageView(
                        urlString: PaintingAssetURL.apiAssetUrl(environment.config.apiBaseURL.absoluteString, imagePath)
                    )
                    .frame(width: containerSize.width, height: containerSize.height)
                } else {
                    TimelineView(.animation(minimumInterval: 1.0 / 60.0, paused: !isAnimating(state))) { timeline in
                        frame(state: state, canvasSize: canvasSize, now: timeline.date)
                    }
                    .frame(width: containerSize.width, height: containerSize.height)
                }

                if !viewOnly, StudioSelectors.shouldShowIdleAnimation(state) {
                    IdleParticlesView()
                        .frame(width: containerSize.width, height: containerSize.height)
                        .allowsHitTesting(false)
                }

                penIndicator(state: state, containerSize: containerSize, canvasSize: canvasSize)

                if gestureEnabled {
                    drawingModePill
                }
            }
            .frame(width: containerSize.width, height: containerSize.height)
            .contentShape(Rectangle())
            .gesture(dragGesture(containerSize: containerSize, canvasSize: canvasSize, enabled: gestureEnabled))
        }
        .aspectRatio(canvasSize.width / max(canvasSize.height, 1), contentMode: .fit)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .shadow(color: Color.black.opacity(0.1), radius: 12, x: 0, y: 4)
        .accessibilityIdentifier("canvas-view")
        .accessibilityLabel(accessibilityLabel(state: state))
    }

    // MARK: - Rendering

    @ViewBuilder
    private func frame(state: StudioState, canvasSize: CGSize, now: Date) -> some View {
        if MonetStudio.hasPainting(state.painting) {
            if let image = paintingController.frame(
                base: state.painting.base,
                playing: state.painting.playing,
                apiBaseURL: environment.config.apiBaseURL,
                now: now,
                onPlaybackDone: { assetBase in
                    environment.studio.paintingPlaybackDone(assetBase: assetBase)
                }
            ) {
                Image(decorative: image, scale: 1)
                    .resizable()
                    .accessibilityHidden(true)
            } else {
                Color.white
            }
        } else if let image = canvasCache.frame(state: state, canvasSize: canvasSize) {
            Image(decorative: image, scale: 1)
                .resizable()
                .accessibilityHidden(true)
        } else {
            Color.white
        }
    }

    private func isAnimating(_ state: StudioState) -> Bool {
        state.performance.onStage != nil || !state.currentStroke.isEmpty || !state.performance.buffer.isEmpty
            || state.painting.playing != nil
    }

    // MARK: - Pen indicator (performer-render spec §9.1)

    @ViewBuilder
    private func penIndicator(state: StudioState, containerSize: CGSize, canvasSize: CGSize) -> some View {
        if let pen = state.performance.penPosition, canvasSize.width > 0 {
            let scale = containerSize.width / canvasSize.width
            let outer: CGFloat = state.performance.penDown ? 6 : 8
            let inner: CGFloat = state.performance.penDown ? 3 : 4
            ZStack {
                Circle()
                    .stroke(CodeMonetDesignSystem.Extra.penIndicator.opacity(0.6), lineWidth: 1.5)
                    .frame(width: outer * 2, height: outer * 2)
                Circle()
                    .fill(CodeMonetDesignSystem.Extra.penIndicator.opacity(0.8))
                    .frame(width: inner * 2, height: inner * 2)
            }
            .position(x: CGFloat(pen.x) * scale, y: CGFloat(pen.y) * scale)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
    }

    // MARK: - Drawing-mode indicator (ux spec §6.2)

    private var drawingModePill: some View {
        Text("Drawing Mode")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(Color.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Capsule().fill(CodeMonetDesignSystem.Extra.coral))
            .padding(8)
            .allowsHitTesting(false)
    }

    // MARK: - Gesture (ux spec §6.2)

    private func dragGesture(containerSize: CGSize, canvasSize: CGSize, enabled: Bool) -> some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                guard enabled else { return }
                let point = canvasPoint(from: value.location, containerSize: containerSize, canvasSize: canvasSize)
                if isDragging {
                    environment.studio.addStrokePoint(point)
                } else {
                    isDragging = true
                    environment.studio.startStroke(at: point)
                }
            }
            .onEnded { _ in
                guard enabled, isDragging else { return }
                isDragging = false
                environment.studio.endStroke()
            }
    }

    /// `screenToCanvas` (ux spec §6.2, `app/src/utils/canvas.ts`).
    private func canvasPoint(from location: CGPoint, containerSize: CGSize, canvasSize: CGSize) -> Point {
        guard containerSize.width > 0, containerSize.height > 0 else { return Point(x: 0, y: 0) }
        let x = Double(location.x) * (Double(canvasSize.width) / Double(containerSize.width))
        let y = Double(location.y) * (Double(canvasSize.height) / Double(containerSize.height))
        return Point(x: x, y: y)
    }

    // MARK: - Accessibility (ux spec §10.9)

    private func accessibilityLabel(state: StudioState) -> String {
        if state.viewingPiece != nil {
            return "Canvas, viewing a saved piece"
        }
        let status = StudioSelectors.agentStatus(state)
        switch status {
        case .idle:
            return state.strokes.isEmpty ? "Canvas, empty" : "Canvas, \(state.strokes.count) strokes, idle"
        case .paused:
            return "Canvas, paused"
        case .error:
            return "Canvas, agent hit an error"
        case .thinking, .executing, .drawing:
            return "Canvas, agent is drawing"
        }
    }
}

/// Wraps `MonetRender.IncrementalCanvasRenderer` behind a per-frame
/// `frame(state:canvasSize:)` call so `CanvasView` never has to replay every
/// committed stroke on every `TimelineView` tick (was `renderer.renderCommitted`
/// over the full `state.strokes` array each frame — O(strokes-in-piece) per
/// frame, exactly the cost `IncrementalCanvasRenderer`'s doc comment warns
/// against). Held as a `@State` object reference on `CanvasView` so its
/// identity — and the baked bitmap inside it — survives across frames;
/// only its *internal* fields mutate per call, never the `@State` binding
/// itself, so driving it from inside the `TimelineView` tick is safe.
///
/// Rebakes from scratch when the canvas size changes, when
/// `(pieceNumber, viewingPiece)` changes (a new/loaded/gallery canvas —
/// covers `NEW_CANVAS`/`LOAD_CANVAS`/`CLEAR_VIEWING`), or whenever
/// `state.strokes` is shorter than what's already baked (a safety net for
/// any other wholesale reset, e.g. `.clear`, without needing to enumerate
/// every such `StudioEvent` here). Otherwise only the newly-appended tail
/// of `state.strokes` is committed.
@MainActor
private final class IncrementalCanvasCache {
    private var renderer: IncrementalCanvasRenderer?
    private var bakedCanvasSize: CGSize = .zero
    private var bakedEpoch = ""
    private var bakedCount = 0

    func frame(state: StudioState, canvasSize: CGSize) -> CGImage? {
        let epoch = "\(state.pieceNumber)|\(state.viewingPiece.map(String.init) ?? "-")"
        if renderer == nil || bakedCanvasSize != canvasSize || bakedEpoch != epoch || state.strokes.count < bakedCount {
            let fresh = IncrementalCanvasRenderer(size: canvasSize, styleConfig: state.styleConfig)
            fresh.commit(state.strokes)
            renderer = fresh
            bakedCanvasSize = canvasSize
            bakedEpoch = epoch
            bakedCount = state.strokes.count
        } else if state.strokes.count > bakedCount {
            renderer?.commit(Array(state.strokes[bakedCount...]))
            bakedCount = state.strokes.count
        }

        return renderer?.renderFrame(inProgressStrokes: Self.inProgressPaths(state: state))
    }

    /// Synthesizes `Path` values for the two in-progress strokes (human
    /// drag + agent's current stroke) so they draw through the same
    /// pipeline as committed ones, without being baked/persisted.
    private static func inProgressPaths(state: StudioState) -> [MonetProtocol.Path] {
        var paths: [MonetProtocol.Path] = []
        if state.currentStroke.count >= 2 {
            paths.append(MonetProtocol.Path(type: .polyline, points: state.currentStroke, author: .human))
        }
        let agentStroke = state.performance.agentStroke
        if agentStroke.count >= 2 {
            let style = state.performance.agentStrokeStyle
            paths.append(MonetProtocol.Path(
                type: .polyline,
                points: agentStroke,
                author: .agent,
                color: style?.color,
                strokeWidth: style?.strokeWidth,
                opacity: style?.opacity
            ))
        }
        return paths
    }
}
