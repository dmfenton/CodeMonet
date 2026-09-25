import CoreGraphics
import CoreImage
import Foundation
import MonetProtocol

/// CoreGraphics drawing glue tying the freehand outline (`PerfectFreehand.
/// swift`), bristles (`Bristles.swift`) and stamp model (`Stamping.swift`)
/// to an actual `CGContext`. All coordinates in are canvas space (top-left
/// origin, y-down, spec §1); every function here flips into the bitmap's
/// native y-up device space itself, so callers never need to.
enum StrokeRendering {
    // -------------------------------------------------------------------
    // Shared coordinate helpers
    // -------------------------------------------------------------------

    /// Canvas-space `Point` -> device-space `CGPoint` for a bitmap of
    /// `height` logical pixels (y-up native CoreGraphics bitmap origin).
    static func devicePoint(_ p: Point, height: Double) -> CGPoint {
        CGPoint(x: p.x, y: height - p.y)
    }

    static func hexColor(_ hex: String, alpha: Double = 1) -> CGColor {
        let rgb = hexToRgb(hex)
        return CGColor(red: Double(rgb.r) / 255, green: Double(rgb.g) / 255, blue: Double(rgb.b) / 255, alpha: alpha)
    }

    static func outlinePath(_ outline: [Point], height: Double) -> CGPath? {
        guard !outline.isEmpty else { return nil }
        let path = CGMutablePath()
        path.move(to: devicePoint(outline[0], height: height))
        for p in outline.dropFirst() {
            path.addLine(to: devicePoint(p, height: height))
        }
        path.closeSubpath()
        return path
    }

    // -------------------------------------------------------------------
    // Plotter-mode / brush-freehand rendering (spec §4, §5, §8.5, §9)
    // -------------------------------------------------------------------

    /// A freehand outline's resolved (options, optional brush preset) pair
    /// — the brush preset drives bristles/main-vs-bristle opacity split,
    /// while `options` already encodes the size/taper/thinning derived from
    /// it (or from the no-brush fallback, spec §4.6).
    public struct PainterlyStrokeConfig: Sendable {
        public var options: FreehandOptions
        public var brushPreset: BrushPreset?

        public init(options: FreehandOptions, brushPreset: BrushPreset?) {
            self.options = options
            self.brushPreset = brushPreset
        }
    }

    /// `PainterlyStroke` (spec §8.5): freehand outline + optional bristles,
    /// used for every completed plotter-mode stroke (`brushPreset == nil`
    /// always, per §8.3/§14) and, by callers outside this package, for the
    /// in-progress and live-human strokes in both modes.
    static func drawPainterlyStroke(
        context: CGContext,
        points: [Point],
        style: StampStrokeStyle,
        config: PainterlyStrokeConfig,
        height: Double
    ) {
        guard !points.isEmpty else { return }
        let outline = getFreehandOutline(points, options: config.options)
        let mainOpacity = config.brushPreset?.mainOpacity ?? 1
        let bristleOpacity = config.brushPreset?.bristleOpacity ?? 0.3

        if let preset = config.brushPreset, preset.bristleCount > 0 {
            let bristles = getBristleOutlines(
                inputPoints: points, bristleCount: preset.bristleCount,
                spread: preset.bristleSpread * config.options.size, options: config.options
            )
            context.setFillColor(hexColor(style.color, alpha: bristleOpacity * style.opacity))
            for bristle in bristles {
                guard let path = outlinePath(bristle, height: height) else { continue }
                context.addPath(path)
                context.fillPath()
            }
        }

        guard let mainPath = outlinePath(outline, height: height) else { return }
        context.setFillColor(hexColor(style.color, alpha: mainOpacity * style.opacity))
        context.addPath(mainPath)
        context.fillPath()
    }

    // -------------------------------------------------------------------
    // Paint-mode stamp rendering (spec §7)
    // -------------------------------------------------------------------

    /// `SkiaStampedStroke`/the web's `drawStampsToContext` (spec §7.6): the
    /// **non-uniform** placement math (web-exact, per the spec's explicit
    /// recommendation for a CoreGraphics port) — `CGContext.clip(to:mask:)`
    /// stretches the cached sprite mask to `(stamp.length, stamp.width)`
    /// independently, with no uniform-scale approximation.
    static func drawStampedStroke(context: CGContext, points: [Point], style: StampStrokeStyle, brush: BrushName?, height: Double) {
        let stamps = computeStrokeStamps(points: points, style: style, brush: brush)
        guard !stamps.isEmpty else { return }
        for stamp in stamps {
            guard let mask = SpriteMaskCache.shared.mask(for: brush, variant: stamp.variant) else { continue }
            context.saveGState()
            context.translateBy(x: stamp.x, y: height - stamp.y)
            // Device space is a mirror of canvas space (y flipped), so the
            // canvas-space tangent angle must be negated to rotate the
            // correct way on screen.
            context.rotate(by: -stamp.angle)
            let rect = CGRect(x: -stamp.length / 2, y: -stamp.width / 2, width: stamp.length, height: stamp.width)
            context.clip(to: rect, mask: mask.image)
            context.setFillColor(
                red: CGFloat(stamp.color.r) / 255, green: CGFloat(stamp.color.g) / 255,
                blue: CGFloat(stamp.color.b) / 255, alpha: CGFloat(stamp.alpha)
            )
            context.fill(rect)
            context.restoreGState()
        }
    }

    // -------------------------------------------------------------------
    // Soft blur halo (spec §8.2, §9: ~1.5px around a stroke pass only)
    // -------------------------------------------------------------------

    private static let ciContext = CIContext(options: [.useSoftwareRenderer: false])

    /// Runs `draw` into a transparent offscreen layer the size of `context`,
    /// Gaussian-blurs it by `radius`, and composites the result back into
    /// `context` (spec §8.2's "~1.5px halo" / §9's paint-mode in-progress
    /// blur). Used sparingly — only the SVG-type paint-mode stroke pass and
    /// the in-progress/live-human paint strokes ever blur; no completed
    /// point-sampled stroke does (spec §8.5).
    static func drawBlurred(context: CGContext, width: Int, height: Int, radius: Double, draw: (CGContext) -> Void) {
        guard width > 0, height > 0 else { return }
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        guard let layer = CGContext(
            data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
            space: colorSpace, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return }
        draw(layer)
        guard let rendered = layer.makeImage() else { return }
        let ciImage = CIImage(cgImage: rendered)
        guard let filter = CIFilter(name: "CIGaussianBlur") else {
            context.draw(rendered, in: CGRect(x: 0, y: 0, width: width, height: height))
            return
        }
        filter.setValue(ciImage, forKey: kCIInputImageKey)
        filter.setValue(radius, forKey: kCIInputRadiusKey)
        guard let output = filter.outputImage else { return }
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        guard let blurredCG = ciContext.createCGImage(output, from: bounds) else { return }
        context.draw(blurredCG, in: bounds)
    }
}
