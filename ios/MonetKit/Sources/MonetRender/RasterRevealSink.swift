import CoreGraphics
import Foundation
import ImageIO
import MonetProtocol

/// Decodes raw image bytes (a keyframe JPEG or `final.png`) to a `CGImage`.
/// Shared by `RasterRevealSink`'s callers so nothing in the app target has
/// to reach for `ImageIO` directly.
public enum PaintingImageDecoder {
    public enum DecodeError: Error, Equatable, Sendable { case invalidData }

    public static func decode(_ data: Data) throws -> CGImage {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else {
            throw DecodeError.invalidData
        }
        return image
    }
}

/// A `RevealSink` that composites a program-painting version's reveal
/// directly into a CoreGraphics bitmap (program-painting spec §4.4-4.5) —
/// the native counterpart of `app/src/renderers/RasterRevealLayer.tsx`'s
/// Skia sink (see that file's doc comment for the shared drawing model:
/// "each stroke as a round-capped/joined stroke painted with the keyframe
/// image as its shader, each area op as a shader-filled rect"). CoreGraphics
/// has no image-shader-fill primitive, so the same effect is achieved with
/// clip-then-draw: set the op's shape as the clip path, then draw the
/// keyframe image across the *whole* canvas rect — only the clipped region
/// actually changes.
///
/// Operates entirely in the manifest's own pixel space (`plan.width` x
/// `plan.height` — see `RevealPlan`'s doc comment): the context is sized to
/// exactly that, one to one with `RevealOp` coordinates, so no scale
/// transform is threaded through every draw call. The caller (the app
/// target's `PaintingRevealController`) is responsible for resizing the
/// composited `CGImage` to the displayed canvas size, exactly as
/// `CanvasView` already does for the committed-strokes layer.
///
/// Bitmap contexts in this package are bottom-left-origin, un-flipped
/// (`CanvasRendering.makeContext`'s doc), matching every other renderer
/// here. `CGContext.draw(_:in:)` — verified empirically, not just by
/// reading the docs, since a persistent-CTM-flip first attempt here got it
/// backwards — draws a decoded image's own row 0 at the *top* of an
/// unflipped context's backing buffer with **no transform needed at all**;
/// only hand-built vector geometry (a clip rect or path in manifest
/// top-left-origin, y-down pixel coordinates) needs the manual `height - y`
/// flip every other renderer in this package already applies before adding
/// it to the context (`CanvasRenderer.swift`'s `fillPath(for:smooth:height:)`
/// uses the identical `CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: 0, ty:
/// height)`, reused verbatim below). So: clip shapes get flipped; the
/// keyframe image itself, drawn full-rect after clipping, never does.
public final class RasterRevealSink: RevealSink {
    public enum InitError: Error, Equatable, Sendable { case contextCreationFailed, imageCountMismatch }

    /// The live composited bitmap.
    public let context: CGContext
    private let plan: RevealPlan
    /// One decoded keyframe image per `plan.keyframes` entry, same index.
    private let images: [CGImage]
    private let canvasRect: CGRect
    /// Maps manifest (top-left-origin, y-down) coordinates to this
    /// unflipped context's own (bottom-left-origin, y-up) space.
    private let flip: CGAffineTransform

    /// - Parameters:
    ///   - plan: Must have one entry in `images` per `plan.keyframes` (same
    ///     order) — the caller decodes each keyframe's file before
    ///     constructing this sink (program-painting spec §4.2's "load
    ///     everything before starting playback" ordering).
    public init(plan: RevealPlan, images: [CGImage]) throws {
        guard images.count == plan.keyframes.count else { throw InitError.imageCountMismatch }
        guard let context = CanvasRendering.makeContext(width: plan.width, height: plan.height) else {
            throw InitError.contextCreationFailed
        }
        self.context = context
        self.plan = plan
        self.images = images
        canvasRect = CGRect(x: 0, y: 0, width: plan.width, height: plan.height)
        flip = CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: 0, ty: CGFloat(plan.height))
        context.clear(canvasRect)
    }

    /// Draws `image` across the full canvas rect — every image draw in this
    /// sink funnels through here. Never flipped: see the type's doc comment.
    private func drawFull(_ image: CGImage) {
        context.draw(image, in: canvasRect)
    }

    /// A manifest-space rect, flipped into context space. Only valid for an
    /// axis-aligned rect whose manifest-space corners are `(x, y0)` and
    /// `(x+w, y1)` with `y0 <= y1` — exactly what every caller below builds.
    private func flippedRect(x: Double, y0: Double, width: Double, y1: Double) -> CGRect {
        let p0 = CGPoint(x: x, y: y0).applying(flip)
        let p1 = CGPoint(x: x + width, y: y1).applying(flip)
        return CGRect(x: p0.x, y: min(p0.y, p1.y), width: p1.x - p0.x, height: abs(p1.y - p0.y))
    }

    // MARK: - RevealSink

    public func revealOps(kf: Int, from: Int, to: Int) {
        guard kf < images.count else { return }
        let image = images[kf]
        for index in from ..< to {
            guard index >= 0, index + 1 < plan.opDataStart.count else { continue }
            let start = plan.opDataStart[index]
            let end = plan.opDataStart[index + 1]
            context.saveGState()
            switch plan.opKind[index] {
            case .area:
                guard end - start == 4 else { context.restoreGState(); continue }
                let x0 = plan.opData[start], y0 = plan.opData[start + 1]
                let x1 = plan.opData[start + 2], y1 = plan.opData[start + 3]
                context.clip(to: flippedRect(x: x0, y0: y0, width: x1 - x0, y1: y1))
            case .stroke:
                guard let clipPath = strokeClipPath(start: start, end: end) else { context.restoreGState(); continue }
                context.addPath(clipPath)
                context.clip()
            }
            drawFull(image)
            context.restoreGState()
        }
    }

    public func settleKeyframe(_ kf: Int) {
        guard kf < images.count else { return }
        drawFull(images[kf])
    }

    public func wipeArea(kf: Int, op: Int, progress: Double) {
        guard kf < images.count, op >= 0, op + 1 < plan.opDataStart.count else { return }
        let start = plan.opDataStart[op]
        let end = plan.opDataStart[op + 1]
        guard end - start == 4 else { return }
        let image = images[kf]
        let x0 = plan.opData[start], y0 = plan.opData[start + 1]
        let x1 = plan.opData[start + 2], y1 = plan.opData[start + 3]
        let height = y1 - y0
        let edge = y0 + height * progress

        context.saveGState()
        context.clip(to: flippedRect(x: x0, y0: y0, width: x1 - x0, y1: max(y0, edge)))
        drawFull(image)
        context.restoreGState()

        // Soft leading edge (mirrors RasterRevealLayer.tsx's WIPE_FEATHER):
        // a translucent band just past the opaque edge, overwritten opaquely
        // by later frames as the wipe continues.
        let featherHeight = min(height * Self.wipeFeather, y1 - edge)
        if featherHeight > 0 {
            context.saveGState()
            context.clip(to: flippedRect(x: x0, y0: edge, width: x1 - x0, y1: edge + featherHeight))
            context.setAlpha(Self.wipeFeatherAlpha)
            drawFull(image)
            context.restoreGState()
        }
    }

    // MARK: - Geometry

    private static let wipeFeather = 0.06
    private static let wipeFeatherAlpha: CGFloat = 0.35

    /// Builds the clip path for a stroke op's `[width, x0,y0, x1,y1, ...]`
    /// data slice: a filled circle for a single point (radius `width/2`),
    /// otherwise a round-capped/joined stroked polyline (program-painting
    /// spec §3.3, `RevealOp.stroke`'s doc comment).
    private func strokeClipPath(start: Int, end: Int) -> CGPath? {
        guard end > start else { return nil }
        let width = plan.opData[start]
        guard width > 0 else { return nil }
        var points: [CGPoint] = []
        var index = start + 1
        while index + 1 < end {
            points.append(CGPoint(x: plan.opData[index], y: plan.opData[index + 1]))
            index += 2
        }
        guard let first = points.first else { return nil }
        let raw: CGPath
        if points.count == 1 {
            let radius = CGFloat(width) / 2
            raw = CGPath(ellipseIn: CGRect(x: first.x - radius, y: first.y - radius, width: radius * 2, height: radius * 2), transform: nil)
        } else {
            let unstroked = CGMutablePath()
            unstroked.move(to: first)
            for point in points.dropFirst() { unstroked.addLine(to: point) }
            raw = unstroked.copy(strokingWithWidth: CGFloat(width), lineCap: .round, lineJoin: .round, miterLimit: 1)
        }
        let flipped = CGMutablePath()
        flipped.addPath(raw, transform: flip)
        return flipped
    }
}
