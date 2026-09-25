import MonetProtocol
import SwiftUI

/// A lightweight, static preview of in-progress strokes for the Continue
/// card (ux spec §5.2's `WipPreview`) — completed strokes only, no
/// animation, single-point strokes render as filled dots. Deliberately not
/// the full painterly/perfect-freehand renderer (`MonetRender`'s job for the
/// live canvas itself); this is a small-scale summary thumbnail, matching
/// the RN version's plain SVG preview.
struct WipPreview: View {
    let strokes: [MonetProtocol.Path]
    let canvasWidth: Int
    let canvasHeight: Int
    let styleConfig: DrawingStyleConfig

    var body: some View {
        Canvas { context, size in
            guard canvasWidth > 0, canvasHeight > 0 else { return }
            let scaleX = size.width / CGFloat(canvasWidth)
            let scaleY = size.height / CGFloat(canvasHeight)
            let scale = min(scaleX, scaleY)
            let offset = CGSize(
                width: (size.width - CGFloat(canvasWidth) * scale) / 2,
                height: (size.height - CGFloat(canvasHeight) * scale) / 2
            )

            for stroke in strokes {
                let effective = styleConfig.effectiveStyle(for: stroke)
                let color = Color(hex: effective.color).opacity(effective.opacity)

                if stroke.type != .svg, stroke.points.count == 1, let point = stroke.points.first {
                    let radius = max(1, effective.strokeWidth / 2) * scale
                    let center = CGPoint(
                        x: CGFloat(point.x) * scale + offset.width,
                        y: CGFloat(point.y) * scale + offset.height
                    )
                    let rect = CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)
                    context.fill(SwiftUI.Path(ellipseIn: rect), with: .color(color))
                    continue
                }

                guard stroke.points.count >= 2 else { continue }
                var path = SwiftUI.Path()
                let first = stroke.points[0]
                path.move(to: CGPoint(x: CGFloat(first.x) * scale + offset.width, y: CGFloat(first.y) * scale + offset.height))
                for point in stroke.points.dropFirst() {
                    path.addLine(to: CGPoint(x: CGFloat(point.x) * scale + offset.width, y: CGFloat(point.y) * scale + offset.height))
                }
                context.stroke(
                    path,
                    with: .color(color),
                    style: StrokeStyle(
                        lineWidth: max(0.5, effective.strokeWidth * scale),
                        lineCap: effective.strokeLinecap == .butt ? .butt : (effective.strokeLinecap == .square ? .square : .round),
                        lineJoin: effective.strokeLinejoin == .miter ? .miter : (effective.strokeLinejoin == .bevel ? .bevel : .round)
                    )
                )
            }
        }
    }
}
