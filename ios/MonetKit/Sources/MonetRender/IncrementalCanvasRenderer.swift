import CoreGraphics
import Foundation
import MonetProtocol

/// Live 60fps rendering support: bakes each newly-committed stroke into a
/// persistent bitmap once, so a per-frame redraw only has to composite that
/// baked bitmap with a freshly-drawn in-progress stroke — not replay every
/// stroke in the piece every frame (the ARCHITECTURE.md data-flow section's
/// "renders live at 60fps" requirement; a full `renderCommitted` replay
/// would be O(strokes-in-piece) per frame, which stops scaling well past a
/// few hundred strokes).
///
/// Not thread-safe — like the SwiftUI/CoreAnimation render loop that will
/// drive it (`CADisplayLink` on `StudioStore`, per ARCHITECTURE.md §2), a
/// single `IncrementalCanvasRenderer` is meant to be owned and driven from
/// one thread/actor at a time (typically the main actor).
public final class IncrementalCanvasRenderer: @unchecked Sendable {
    private let width: Int
    private let height: Int
    private let styleConfig: DrawingStyleConfig
    private var bakedContext: CGContext?
    private var committedCount = 0

    public init(size: CGSize, styleConfig: DrawingStyleConfig) {
        width = max(1, Int(size.width))
        height = max(1, Int(size.height))
        self.styleConfig = styleConfig
        bakedContext = CanvasRendering.makeContext(width: width, height: height)
        if let context = bakedContext {
            CanvasRendering.fillWhite(context, width: width, height: height)
        }
    }

    /// Number of strokes baked into the current bitmap so far.
    public var committedStrokeCount: Int { committedCount }

    /// Bakes one more completed stroke into the persistent bitmap. Call
    /// this once per stroke as it's committed (e.g. on `STROKE_COMPLETE`) —
    /// not every frame.
    public func commit(_ path: Path) {
        guard let context = bakedContext else { return }
        CanvasRendering.drawCompletedPath(path, into: context, styleConfig: styleConfig, canvasSize: CGSize(width: width, height: height))
        committedCount += 1
    }

    /// Bakes several strokes in one call, e.g. replaying a loaded gallery
    /// piece's saved strokes before live drawing resumes.
    public func commit(_ paths: [Path]) {
        for path in paths { commit(path) }
    }

    /// Renders one frame: the baked bitmap plus an optional freshly-drawn
    /// in-progress stroke composited on top. The baked bitmap itself is
    /// never mutated by this call — cost is O(in-progress stroke), not
    /// O(strokes-in-piece).
    public func renderFrame(inProgress: Path? = nil) -> CGImage? {
        guard let baked = bakedContext?.makeImage() else { return nil }
        guard let frame = CanvasRendering.makeContext(width: width, height: height) else { return baked }
        let rect = CGRect(x: 0, y: 0, width: width, height: height)
        frame.draw(baked, in: rect)
        if let inProgress {
            let size = CGSize(width: width, height: height)
            CanvasRendering.drawCompletedPath(inProgress, into: frame, styleConfig: styleConfig, canvasSize: size)
        }
        return frame.makeImage()
    }

    /// Discards every baked stroke and starts over — a new canvas, or a
    /// `LOAD_CANVAS` that's about to replay a different piece's strokes.
    public func reset() {
        bakedContext = CanvasRendering.makeContext(width: width, height: height)
        if let context = bakedContext {
            CanvasRendering.fillWhite(context, width: width, height: height)
        }
        committedCount = 0
    }
}
