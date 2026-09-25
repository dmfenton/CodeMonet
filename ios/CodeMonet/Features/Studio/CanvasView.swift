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
    private let renderer: any CanvasRenderer = CoreGraphicsCanvasRenderer()

    @State private var isDragging = false

    var body: some View {
        let state = environment.studio.state
        let canvasSize = CGSize(width: state.canvasWidth, height: state.canvasHeight)
        let viewOnly = state.viewingPiece != nil
        let gestureEnabled = drawingEnabled && !viewOnly

        GeometryReader { proxy in
            let containerSize = CGSize(width: proxy.size.width, height: proxy.size.width * canvasSize.height / max(canvasSize.width, 1))

            ZStack(alignment: .topLeading) {
                TimelineView(.animation(minimumInterval: 1.0 / 60.0, paused: !isAnimating(state))) { _ in
                    frame(state: state, canvasSize: canvasSize)
                }
                .frame(width: containerSize.width, height: containerSize.height)

                if !viewOnly, StudioSelectors.shouldShowIdleAnimation(state) {
                    IdleParticlesView(canvasSize: canvasSize)
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
    private func frame(state: StudioState, canvasSize: CGSize) -> some View {
        if let image = renderer.renderCommitted(strokes: renderPaths(state: state), styleConfig: state.styleConfig, size: canvasSize) {
            Image(decorative: image, scale: 1)
                .resizable()
                .accessibilityHidden(true)
        } else {
            Color.white
        }
    }

    /// Committed strokes plus the two in-progress strokes, synthesized as
    /// `Path` values so `CanvasRenderer` draws all three through the one
    /// pipeline (performer-render spec §9's in-progress rendering is the
    /// renderer package's job to make visually rich; here we just supply
    /// the geometry it needs).
    private func renderPaths(state: StudioState) -> [MonetProtocol.Path] {
        var paths = state.strokes
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

    private func isAnimating(_ state: StudioState) -> Bool {
        state.performance.onStage != nil || !state.currentStroke.isEmpty || !state.performance.buffer.isEmpty
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
