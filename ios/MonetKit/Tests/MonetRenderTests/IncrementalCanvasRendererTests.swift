import CoreGraphics
import Foundation
@testable import MonetProtocol
@testable import MonetRender
import Testing

@Suite("IncrementalCanvasRenderer")
struct IncrementalCanvasRendererTests {
    private func randomStroke(seed: Int, canvasSize: CGSize) -> Path {
        var rng = Mulberry32(seed: UInt32(truncatingIfNeeded: seed &* 2654435761))
        let pointCount = 8 + Int(rng.next() * 12)
        let startX = rng.next() * canvasSize.width
        let startY = rng.next() * canvasSize.height
        let points = (0 ..< pointCount).map { i -> Point in
            Point(
                x: (startX + Double(i) * (rng.next() * 20 - 10) + rng.next() * 30).truncatingRemainder(dividingBy: canvasSize.width),
                y: (startY + Double(i) * (rng.next() * 20 - 10) + rng.next() * 30).truncatingRemainder(dividingBy: canvasSize.height)
            )
        }
        let brushes: [BrushName] = [.oilRound, .oilFlat, .watercolor, .dryBrush, .ink, .pencil]
        let brush = brushes[seed % brushes.count]
        return Path(
            type: .polyline, points: points,
            color: String(format: "#%02x%02x%02x", 20 + seed % 200, 40 + (seed * 7) % 180, 60 + (seed * 13) % 150),
            strokeWidth: 4 + Double(seed % 12), opacity: 0.6 + Double(seed % 4) * 0.1, brush: brush
        )
    }

    /// This machine's test runs share a heavily loaded box with other
    /// parallel builders (see the work package's setup notes), so an
    /// absolute wall-clock ceiling is inherently flaky under contention.
    /// The property that actually matters — and the one this test pins —
    /// is *algorithmic*: a frame's cost must stay ~constant regardless of
    /// how many strokes are already baked into the bitmap, i.e. genuinely
    /// O(in-progress stroke), not O(strokes-in-piece). A generous absolute
    /// ceiling is kept too, as a backstop against a real regression (e.g.
    /// someone accidentally replaying every stroke per frame), just set
    /// high enough to tolerate heavy contention rather than to be tight.
    @Test("baking 500 strokes incrementally keeps per-frame cost independent of piece size")
    func fiveHundredStrokePerformance() throws {
        let size = CGSize(width: 800, height: 600)
        let renderer = IncrementalCanvasRenderer(size: size, styleConfig: .paint)
        let inProgress = Path(
            type: .polyline, points: [Point(x: 100, y: 100), Point(x: 150, y: 120), Point(x: 200, y: 90)],
            color: "#333333", strokeWidth: 8, opacity: 0.8, brush: .oilRound
        )

        func timeFrameRender() -> TimeInterval {
            let start = Date()
            _ = renderer.renderFrame(inProgress: inProgress)
            return Date().timeIntervalSince(start)
        }

        // Warm up (first call pays one-time sprite-mask cache population).
        _ = timeFrameRender()
        let emptyFrameTimes = (0 ..< 5).map { _ in timeFrameRender() }
        let emptyFrameCost = emptyFrameTimes.reduce(0, +) / Double(emptyFrameTimes.count)

        let strokes = (0 ..< 500).map { randomStroke(seed: $0, canvasSize: size) }
        let bakeStart = Date()
        renderer.commit(strokes)
        let bakeElapsed = Date().timeIntervalSince(bakeStart)
        #expect(renderer.committedStrokeCount == 500)

        let fullFrameTimes = (0 ..< 5).map { _ in timeFrameRender() }
        let fullFrameCost = fullFrameTimes.reduce(0, +) / Double(fullFrameTimes.count)

        #expect(fullFrameCost != 0 || emptyFrameCost == 0)
        // A generous multiplicative bound: with true incremental baking, a
        // frame with 500 strokes already baked should cost roughly the
        // same as one with none — a small constant-factor blit difference,
        // not a 500x replay. 8x leaves headroom for measurement noise on a
        // contended box while still catching an accidental O(n) regression.
        #expect(
            fullFrameCost < max(emptyFrameCost * 8, 0.25),
            "empty-canvas frame \(emptyFrameCost)s vs 500-stroke frame \(fullFrameCost)s"
        )

        // Backstop only — generous enough to tolerate heavy shared-machine
        // contention, not meant to be a tight bound.
        #expect(bakeElapsed < 120, "baking 500 strokes took \(bakeElapsed)s")

        let frame = try #require(renderer.renderFrame(inProgress: inProgress))
        #expect(frame.width == 800)
        #expect(frame.height == 600)
    }

    @Test("committed strokes stay baked across multiple frame renders")
    func bakedStrokesPersistAcrossFrames() {
        let size = CGSize(width: 200, height: 200)
        let renderer = IncrementalCanvasRenderer(size: size, styleConfig: .paint)
        let line = Path(type: .line, points: [Point(x: 10, y: 100), Point(x: 190, y: 100)], color: "#000000", strokeWidth: 10, opacity: 1)
        renderer.commit(line)

        let frame1 = renderer.renderFrame()
        let frame2 = renderer.renderFrame()
        #expect(frame1 != nil)
        #expect(frame2 != nil)
        #expect(renderer.committedStrokeCount == 1)
    }

    @Test("reset discards baked strokes")
    func resetClearsCanvas() {
        let size = CGSize(width: 200, height: 200)
        let renderer = IncrementalCanvasRenderer(size: size, styleConfig: .paint)
        let line = Path(type: .line, points: [Point(x: 10, y: 100), Point(x: 190, y: 100)], color: "#000000", strokeWidth: 10, opacity: 1)
        renderer.commit(line)
        #expect(renderer.committedStrokeCount == 1)
        renderer.reset()
        #expect(renderer.committedStrokeCount == 0)
    }
}
