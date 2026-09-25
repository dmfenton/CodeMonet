import CoreGraphics
import Foundation
import MonetProtocol

/// Renders a committed set of strokes (and, separately, one in-progress
/// stroke) to a `CGImage`, deterministically, given `(strokes, styleConfig,
/// size)` — no UIKit/AppKit/SwiftUI dependency, so it runs identically from
/// the `CodeMonet` app target, `monet-render` CLI, and `swift test`.
///
/// This protocol is the frozen contract for the **renderer** work package
/// (see ../../../ARCHITECTURE.md). `CoreGraphicsCanvasRenderer` below is a
/// functioning-but-simplified placeholder body — it strokes each path's
/// sampled points directly rather than running the full perfect-freehand /
/// stamp pipeline (performer-render spec §4-§9) — so the app and
/// `monet-render` both compile and produce a real (if visually simplified)
/// PNG today. The renderer package replaces the body, not the signature.
public protocol CanvasRenderer: Sendable {
    /// Rasterizes `strokes` at `size` (canvas-space pixels, e.g. 800x600 —
    /// no retina/DPI scaling baked in, matching performer-render spec §15.3)
    /// against a white background.
    func renderCommitted(strokes: [Path], styleConfig: DrawingStyleConfig, size: CGSize) -> CGImage?
}

/// Default `CanvasRenderer`. See the protocol doc for what's a placeholder
/// vs. a frozen contract.
public struct CoreGraphicsCanvasRenderer: CanvasRenderer {
    public init() {}

    public func renderCommitted(strokes: [Path], styleConfig: DrawingStyleConfig, size: CGSize) -> CGImage? {
        let width = max(1, Int(size.width))
        let height = max(1, Int(size.height))
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        guard let context = CGContext(
            data: nil,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return nil }

        context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))

        for path in strokes {
            let style = styleConfig.effectiveStyle(for: path)
            let points = PathSampling.samplePoints(path)
            guard points.count >= 2 else { continue }
            let cgPath = CGMutablePath()
            cgPath.move(to: CGPoint(x: points[0].x, y: Double(height) - points[0].y))
            for point in points.dropFirst() {
                cgPath.addLine(to: CGPoint(x: point.x, y: Double(height) - point.y))
            }
            context.addPath(cgPath)
            context.setStrokeColor(Self.cgColor(hex: style.color, alpha: style.opacity))
            context.setLineWidth(style.strokeWidth)
            context.setLineCap(style.strokeLinecap == .round ? .round : (style.strokeLinecap == .square ? .square : .butt))
            context.setLineJoin(style.strokeLinejoin == .round ? .round : (style.strokeLinejoin == .bevel ? .bevel : .miter))
            context.strokePath()
        }

        return context.makeImage()
    }

    private static func cgColor(hex: String, alpha: Double) -> CGColor {
        var sanitized = hex.trimmingCharacters(in: .whitespaces)
        if sanitized.hasPrefix("#") { sanitized.removeFirst() }
        guard sanitized.count == 6, let value = UInt32(sanitized, radix: 16) else {
            return CGColor(red: 0, green: 0, blue: 0, alpha: alpha)
        }
        let r = Double((value >> 16) & 0xFF) / 255.0
        let g = Double((value >> 8) & 0xFF) / 255.0
        let b = Double(value & 0xFF) / 255.0
        return CGColor(red: r, green: g, blue: b, alpha: alpha)
    }
}
