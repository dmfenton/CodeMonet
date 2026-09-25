import MonetRender
import SwiftUI

/// Hosts `MonetRender.CanvasRenderer` inside SwiftUI (ux spec §6.2). This
/// re-renders the full committed-strokes bitmap on every `strokes` change —
/// a correct-but-not-yet-incremental placeholder (ARCHITECTURE.md notes the
/// renderer package's job is the incremental committed/in-progress split).
struct CanvasView: View {
    @Environment(AppEnvironment.self) private var environment
    private let renderer: any CanvasRenderer = CoreGraphicsCanvasRenderer()

    var body: some View {
        GeometryReader { proxy in
            let state = environment.studio.state
            let size = CGSize(width: state.canvasWidth, height: state.canvasHeight)
            Group {
                if let image = renderer.renderCommitted(strokes: state.strokes, styleConfig: state.styleConfig, size: size) {
                    Image(decorative: image, scale: 1)
                        .resizable()
                        .aspectRatio(size.width / size.height, contentMode: .fit)
                } else {
                    Color.white
                }
            }
            .frame(width: proxy.size.width, height: proxy.size.width * size.height / size.width)
        }
        .aspectRatio(
            Double(environment.studio.state.canvasWidth) / Double(environment.studio.state.canvasHeight),
            contentMode: .fit
        )
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .accessibilityIdentifier("canvas-view")
    }
}
