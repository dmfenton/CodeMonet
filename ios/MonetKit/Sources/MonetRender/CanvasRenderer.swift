import CoreGraphics
import Foundation
import MonetProtocol

/// Renders a committed set of strokes (and, separately, one in-progress
/// stroke) to a `CGImage`, deterministically, given `(strokes, styleConfig,
/// size)` — no UIKit/AppKit/SwiftUI dependency, so it runs identically from
/// the `CodeMonet` app target, `monet-render` CLI, and `swift test`.
///
/// This protocol is the frozen contract for the **renderer** work package
/// (see ../../../ARCHITECTURE.md). `CoreGraphicsCanvasRenderer` implements
/// the full completed-stroke render dispatch (performer-render spec §8):
/// perfect-freehand outlines for plotter-mode strokes (§4, §8.5), the stamp
/// model for paint-mode strokes (§7, §8.3), and real vector-path handling
/// for `svg`-type strokes (§8.2). `IncrementalCanvasRenderer` (below) is the
/// same per-path drawing logic wrapped for the app's live 60fps loop: it
/// bakes each newly-committed stroke into a persistent bitmap once, so a
/// frame only has to redraw the in-progress stroke, not the whole piece.
public protocol CanvasRenderer: Sendable {
    /// Rasterizes `strokes` at `size` (canvas-space pixels, e.g. 800x600 —
    /// no retina/DPI scaling baked in, matching performer-render spec §15.3)
    /// against a white background.
    func renderCommitted(strokes: [Path], styleConfig: DrawingStyleConfig, size: CGSize) -> CGImage?
}

/// Default `CanvasRenderer`.
public struct CoreGraphicsCanvasRenderer: CanvasRenderer {
    public init() {}

    public func renderCommitted(strokes: [Path], styleConfig: DrawingStyleConfig, size: CGSize) -> CGImage? {
        let width = max(1, Int(size.width))
        let height = max(1, Int(size.height))
        guard let context = CanvasRendering.makeContext(width: width, height: height) else { return nil }
        CanvasRendering.fillWhite(context, width: width, height: height)
        for path in strokes {
            CanvasRendering.drawCompletedPath(path, into: context, styleConfig: styleConfig, canvasSize: size)
        }
        return context.makeImage()
    }
}

/// Shared plumbing between `CoreGraphicsCanvasRenderer` and
/// `IncrementalCanvasRenderer` — one committed `Path`'s full render dispatch
/// (performer-render spec §8), independent of whether it's drawn into a
/// scratch context (static export) or a persistent baked bitmap
/// (incremental/live rendering).
enum CanvasRendering {
    static func makeContext(width: Int, height: Int) -> CGContext? {
        CGContext(
            data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
    }

    static func fillWhite(_ context: CGContext, width: Int, height: Int) {
        context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    }

    /// `SkiaRenderer.tsx`'s per-stroke completed-render dispatch
    /// (performer-render spec §8): style resolution, then one of the SVG
    /// vector path, dot, fill, or stroke (stamp/freehand) passes.
    static func drawCompletedPath(_ path: Path, into context: CGContext, styleConfig: DrawingStyleConfig, canvasSize: CGSize) {
        let height = Double(canvasSize.height)
        let style = styleConfig.effectiveStyle(for: path)
        let isPaintMode = styleConfig.type == .paint

        if path.type == .svg {
            drawSVGPath(path, style: style, isPaintMode: isPaintMode, context: context, canvasSize: canvasSize)
            return
        }

        let points = PathSampling.samplePoints(path)
        guard !points.isEmpty else { return }

        if points.count == 1 {
            drawDot(points[0], radius: max(style.strokeWidth / 2, 1.5), style: style, context: context, height: height)
            return
        }

        let fillPath = fillPath(for: path, smooth: isPaintMode, height: height)

        if let fill = path.fill, style.strokeWidth <= 0 {
            if let fillPath {
                context.setFillColor(StrokeRendering.hexColor(fill, alpha: path.fillOpacity ?? style.opacity))
                context.addPath(fillPath)
                context.fillPath()
            }
            return
        }

        if let fill = path.fill, let fillPath {
            context.setFillColor(StrokeRendering.hexColor(fill, alpha: path.fillOpacity ?? style.opacity))
            context.addPath(fillPath)
            context.fillPath()
        }

        if isPaintMode {
            let stampStyle = StampStrokeStyle(color: style.color, strokeWidth: style.strokeWidth, opacity: style.opacity)
            StrokeRendering.drawStampedStroke(context: context, points: points, style: stampStyle, brush: path.brush, height: height)
        } else {
            // Plotter mode never applies a brush preset (spec §8.3/§14),
            // regardless of what `path.brush` carries.
            let options = FreehandPresets.painterlyDefault(size: style.strokeWidth)
            let plotterStyle = StampStrokeStyle(color: style.color, strokeWidth: style.strokeWidth, opacity: style.opacity)
            let config = StrokeRendering.PainterlyStrokeConfig(options: options, brushPreset: nil)
            StrokeRendering.drawPainterlyStroke(context: context, points: points, style: plotterStyle, config: config, height: height)
        }
    }

    private static func drawDot(_ point: Point, radius: Double, style: StrokeStyle, context: CGContext, height: Double) {
        let center = StrokeRendering.devicePoint(point, height: height)
        let rect = CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)
        context.setFillColor(StrokeRendering.hexColor(style.color, alpha: style.opacity))
        context.fillEllipse(in: rect)
    }

    /// `pathToSvgD(path, smooth)`'s geometry (spec §8.4), built directly as
    /// a device-space `CGPath` instead of an SVG string. Only feeds the
    /// `fill` pass — stroke geometry always comes from `samplePathPoints`.
    private static func fillPath(for path: Path, smooth: Bool, height: Double) -> CGPath? {
        guard path.fill != nil, !path.points.isEmpty else { return nil }
        let raw: CGPath
        if path.type == .polyline, smooth, path.points.count > 2 {
            raw = StrokeSmoothing.catmullRomPath(path.points)
        } else {
            let mutable = CGMutablePath()
            switch path.type {
            case .line:
                guard path.points.count >= 2 else { return nil }
                mutable.move(to: cgPoint(path.points[0]))
                mutable.addLine(to: cgPoint(path.points[1]))
            case .polyline:
                guard !path.points.isEmpty else { return nil }
                mutable.move(to: cgPoint(path.points[0]))
                for p in path.points.dropFirst() { mutable.addLine(to: cgPoint(p)) }
            case .quadratic:
                guard path.points.count >= 3 else { return nil }
                mutable.move(to: cgPoint(path.points[0]))
                mutable.addQuadCurve(to: cgPoint(path.points[2]), control: cgPoint(path.points[1]))
            case .cubic:
                guard path.points.count >= 4 else { return nil }
                mutable.move(to: cgPoint(path.points[0]))
                mutable.addCurve(to: cgPoint(path.points[3]), control1: cgPoint(path.points[1]), control2: cgPoint(path.points[2]))
            case .svg:
                return nil
            }
            raw = mutable
        }
        let flip = CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: 0, ty: CGFloat(height))
        let flipped = CGMutablePath()
        flipped.addPath(raw, transform: flip)
        return flipped
    }

    private static func cgPoint(_ p: Point) -> CGPoint { CGPoint(x: p.x, y: p.y) }

    /// `type === 'svg'` dispatch (spec §8.2): parse `d` once, fill (if set)
    /// then stroke, with a ~1.5px halo blur around the stroke pass only in
    /// paint mode.
    private static func drawSVGPath(_ path: Path, style: StrokeStyle, isPaintMode: Bool, context: CGContext, canvasSize: CGSize) {
        guard let d = path.d, let raw = SVGPathParser.parse(d) else { return }
        let height = Double(canvasSize.height)
        let flip = CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: 0, ty: CGFloat(height))
        let flipped = CGMutablePath()
        flipped.addPath(raw, transform: flip)

        if let fill = path.fill {
            context.setFillColor(StrokeRendering.hexColor(fill, alpha: path.fillOpacity ?? style.opacity))
            context.addPath(flipped)
            context.fillPath()
        }

        guard style.strokeWidth > 0 else { return }
        let strokeDraw: (CGContext) -> Void = { ctx in
            ctx.addPath(flipped)
            ctx.setStrokeColor(StrokeRendering.hexColor(style.color, alpha: style.opacity))
            ctx.setLineWidth(style.strokeWidth)
            ctx.setLineCap(cgLineCap(style.strokeLinecap))
            ctx.setLineJoin(cgLineJoin(style.strokeLinejoin))
            ctx.strokePath()
        }
        if isPaintMode {
            StrokeRendering.drawBlurred(
                context: context, width: Int(canvasSize.width), height: Int(canvasSize.height),
                radius: 1.5, draw: strokeDraw
            )
        } else {
            strokeDraw(context)
        }
    }

    static func cgLineCap(_ cap: StrokeLinecap) -> CGLineCap {
        switch cap {
        case .round: return .round
        case .square: return .square
        case .butt: return .butt
        }
    }

    static func cgLineJoin(_ join: StrokeLinejoin) -> CGLineJoin {
        switch join {
        case .round: return .round
        case .bevel: return .bevel
        case .miter: return .miter
        }
    }
}
