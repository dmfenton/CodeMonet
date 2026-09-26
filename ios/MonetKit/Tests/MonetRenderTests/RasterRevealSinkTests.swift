import CoreGraphics
import Foundation
@testable import MonetProtocol
@testable import MonetRender
import Testing

private struct RGB { var r: UInt8, g: UInt8, b: UInt8 }
private struct RGBA { var r: UInt8, g: UInt8, b: UInt8, a: UInt8 }
private enum TestFixtureError: Error { case creationFailed }

/// A small solid-color synthetic "photo": constructed directly from raw
/// bytes (never drawn through a `CGContext`), so row 0 of the buffer is,
/// unambiguously, the image's own visual top — exactly like a real decoded
/// JPEG/PNG keyframe. Used to pin down `RasterRevealSink`'s orientation
/// without a second, ambiguous "draw this CGImage into a fresh context"
/// step in the test itself (see `RasterRevealSink`'s doc comment on why a
/// context-drawn image and a raw-bytes image aren't interchangeable here).
private func solidHalvesImage(width: Int, height: Int, top: RGB, bottom: RGB) throws -> CGImage {
    var bytes = [UInt8](repeating: 0, count: width * height * 4)
    for y in 0 ..< height {
        let color = y < height / 2 ? top : bottom
        for x in 0 ..< width {
            let offset = (y * width + x) * 4
            bytes[offset] = color.r
            bytes[offset + 1] = color.g
            bytes[offset + 2] = color.b
            bytes[offset + 3] = 255
        }
    }
    guard let provider = CGDataProvider(data: Data(bytes) as CFData),
          let image = CGImage(
              width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: width * 4,
              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
              provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent
          )
    else {
        throw TestFixtureError.creationFailed
    }
    return image
}

/// Reads a pixel directly out of `sink.context.data` — never redraws the
/// composited image through another context (see the orientation note
/// above).
private func pixel(_ sink: RasterRevealSink, x: Int, y: Int, width: Int) throws -> RGBA {
    guard let base = sink.context.data else { throw TestFixtureError.creationFailed }
    let buffer = base.bindMemory(to: UInt8.self, capacity: sink.context.height * sink.context.bytesPerRow)
    let offset = y * sink.context.bytesPerRow + x * 4
    return RGBA(r: buffer[offset], g: buffer[offset + 1], b: buffer[offset + 2], a: buffer[offset + 3])
}

@Suite("RasterRevealSink")
struct RasterRevealSinkTests {
    /// `settleKeyframe` draws the keyframe image "in full" — this pins down
    /// that it lands right-side up: the source image's own top half (red)
    /// ends up at the composited bitmap's top rows, not its bottom ones.
    /// A sink that omitted (or reversed) the vertical-flip transform would
    /// composite this upside down and fail here.
    @Test("settleKeyframe draws the image right-side up, not flipped")
    func settleKeyframeOrientation() throws {
        let width = 20, height = 20
        let image = try solidHalvesImage(width: width, height: height, top: RGB(r: 255, g: 0, b: 0), bottom: RGB(r: 0, g: 0, b: 255))
        let manifest = RevealManifest(width: width, height: height, keyframes: [
            RevealKeyframe(label: "a", image: "kf_00.jpg", ops: []),
        ])
        let plan = buildRevealPlan(manifest)
        let sink = try RasterRevealSink(plan: plan, images: [image])
        sink.settleKeyframe(0)

        let top = try pixel(sink, x: 10, y: 2, width: width)
        #expect(top.r > 200 && top.b < 50, "expected the source image's top-half red near the composited bitmap's top row")

        let bottom = try pixel(sink, x: 10, y: 17, width: width)
        #expect(bottom.b > 200 && bottom.r < 50, "expected the source image's bottom-half blue near the composited bitmap's bottom row")
    }

    /// A stroke op only reveals within its own clip shape — pixels outside
    /// it stay untouched (transparent) even after the op runs.
    @Test("revealOps only paints within the op's own shape")
    func revealOpsClipsToShape() throws {
        let width = 40, height = 40
        let image = try solidHalvesImage(width: width, height: height, top: RGB(r: 255, g: 0, b: 0), bottom: RGB(r: 255, g: 0, b: 0))
        let manifest = RevealManifest(width: width, height: height, keyframes: [
            RevealKeyframe(label: "a", image: "kf_00.jpg", ops: [
                .stroke(width: 4, points: [Point(x: 20, y: 20)]), // a single-point dot
            ]),
        ])
        let plan = buildRevealPlan(manifest)
        let sink = try RasterRevealSink(plan: plan, images: [image])
        sink.revealOps(kf: 0, from: 0, to: 1)

        let inside = try pixel(sink, x: 20, y: 20, width: width)
        #expect(inside.a > 0, "the dot's own center should be painted")

        let outside = try pixel(sink, x: 2, y: 2, width: width)
        #expect(outside.a == 0, "far outside the dot's radius should still be untouched (transparent)")
    }

    /// A stroke placed in the manifest's top half should reveal the source
    /// image's own top-half color there, not its bottom-half color —
    /// confirms the stroke clip path's flip agrees with the image draw's
    /// (lack of one), the same cross-check `wipeAreaPartialProgress` does
    /// for area ops.
    @Test("a stroke near the manifest's top reveals the source image's own top content")
    func strokeRevealsCorrectVerticalPlacement() throws {
        let width = 40, height = 40
        let image = try solidHalvesImage(width: width, height: height, top: RGB(r: 0, g: 200, b: 0), bottom: RGB(r: 200, g: 0, b: 0))
        let manifest = RevealManifest(width: width, height: height, keyframes: [
            RevealKeyframe(label: "a", image: "kf_00.jpg", ops: [
                .stroke(width: 6, points: [Point(x: 20, y: 3)]),
            ]),
        ])
        let plan = buildRevealPlan(manifest)
        let sink = try RasterRevealSink(plan: plan, images: [image])
        sink.revealOps(kf: 0, from: 0, to: 1)

        let dot = try pixel(sink, x: 20, y: 3, width: width)
        #expect(dot.a > 0)
        #expect(dot.g > 150 && dot.r < 50, "a dot near manifest y=3 (top) should show the source image's top-half color")
    }

    /// An area op reveals the full rect it names.
    @Test("revealOps fills an area op's full rect")
    func revealOpsAreaFillsRect() throws {
        let width = 40, height = 40
        let image = try solidHalvesImage(width: width, height: height, top: RGB(r: 0, g: 200, b: 0), bottom: RGB(r: 0, g: 200, b: 0))
        let manifest = RevealManifest(width: width, height: height, keyframes: [
            RevealKeyframe(label: "a", image: "kf_00.jpg", ops: [
                .area(x0: 5, y0: 5, x1: 35, y1: 35),
            ]),
        ])
        let plan = buildRevealPlan(manifest)
        let sink = try RasterRevealSink(plan: plan, images: [image])
        sink.revealOps(kf: 0, from: 0, to: 1)

        for (x, y) in [(6, 6), (20, 20), (34, 34)] {
            let p = try pixel(sink, x: x, y: y, width: width)
            #expect(p.g > 150 && p.a > 0, "(\(x),\(y)) inside the area rect should be filled")
        }
        let outside = try pixel(sink, x: 1, y: 1, width: width)
        #expect(outside.a == 0, "outside the area rect should stay untouched")
    }

    /// `wipeArea` at a partial progress only reveals the top fraction of the
    /// op's rect (program-painting spec §4.4's "top-to-bottom wipe
    /// preview"); the bottom of the rect stays untouched until progress
    /// advances further.
    @Test("wipeArea reveals only the top fraction of the rect, with the source image's own top content, at partial progress")
    func wipeAreaPartialProgress() throws {
        let width = 40, height = 40
        // Distinct top/bottom colors so this also confirms the revealed
        // pixels carry the source image's *own* top content, not just "some
        // alpha" — the clip rect and the drawn image must agree on which
        // end of the manifest's y-axis is "top".
        let image = try solidHalvesImage(width: width, height: height, top: RGB(r: 0, g: 200, b: 0), bottom: RGB(r: 200, g: 0, b: 0))
        let manifest = RevealManifest(width: width, height: height, keyframes: [
            RevealKeyframe(label: "a", image: "kf_00.jpg", ops: [
                .area(x0: 0, y0: 0, x1: Double(width), y1: Double(height)),
            ]),
        ])
        let plan = buildRevealPlan(manifest)
        let sink = try RasterRevealSink(plan: plan, images: [image])
        sink.wipeArea(kf: 0, op: 0, progress: 0.25)

        let nearTop = try pixel(sink, x: 20, y: 2, width: width)
        #expect(nearTop.a > 0, "well within the revealed top fraction should be painted")
        #expect(nearTop.g > 150 && nearTop.r < 50, "the revealed top fraction should show the source image's own top-half color")

        let nearBottom = try pixel(sink, x: 20, y: 38, width: width)
        #expect(nearBottom.a == 0, "past the wipe's current edge should still be untouched")
    }

    @Test("init rejects an images array that doesn't match the plan's keyframe count")
    func rejectsImageCountMismatch() throws {
        let manifest = RevealManifest(width: 10, height: 10, keyframes: [
            RevealKeyframe(label: "a", image: "kf_00.jpg", ops: []),
            RevealKeyframe(label: "b", image: "kf_01.jpg", ops: []),
        ])
        let plan = buildRevealPlan(manifest)
        let image = try solidHalvesImage(width: 10, height: 10, top: RGB(r: 0, g: 0, b: 0), bottom: RGB(r: 0, g: 0, b: 0))
        #expect(throws: RasterRevealSink.InitError.imageCountMismatch) {
            _ = try RasterRevealSink(plan: plan, images: [image])
        }
    }
}
