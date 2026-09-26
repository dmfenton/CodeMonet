import Foundation
@testable import MonetProtocol
@testable import MonetRender
import Testing

@Suite("computeStrokeStamps")
struct StampingTests {
    @Test("too few points or non-positive opacity produce no stamps")
    func guardClauses() {
        let style = StampStrokeStyle(color: "#000000", strokeWidth: 8, opacity: 0.5)
        #expect(computeStrokeStamps(points: [], style: style, brush: nil).isEmpty)
        #expect(computeStrokeStamps(points: [Point(x: 0, y: 0)], style: style, brush: nil).isEmpty)
        let zeroOpacity = StampStrokeStyle(color: "#000000", strokeWidth: 8, opacity: 0)
        let points = [Point(x: 0, y: 0), Point(x: 10, y: 0)]
        #expect(computeStrokeStamps(points: points, style: zeroOpacity, brush: nil).isEmpty)
    }

    @Test("deterministic for identical input")
    func deterministic() {
        let points = (0 ... 20).map { Point(x: Double($0) * 6, y: 10 * sin(Double($0) * 0.3)) }
        let style = StampStrokeStyle(color: "#2d4a6b", strokeWidth: 12, opacity: 0.9)
        let a = computeStrokeStamps(points: points, style: style, brush: .oilRound)
        let b = computeStrokeStamps(points: points, style: style, brush: .oilRound)
        #expect(a.count == b.count)
        for (sa, sb) in zip(a, b) {
            #expect(sa.x == sb.x)
            #expect(sa.y == sb.y)
            #expect(sa.alpha == sb.alpha)
            #expect(sa.color == sb.color)
            #expect(sa.variant == sb.variant)
        }
    }

    /// Cross-checked numerically against an independent line-by-line port
    /// of `stamping.ts` (Python and a standalone Swift script, both
    /// matching to 6 decimal places) for this exact input — see the
    /// renderer work package's report for the verification scripts. Pins
    /// the RNG consumption order (spec §7.4's note: `smoothNoise`'s knots,
    /// then `load` -> `dryness` -> `jitterColor`'s 3 draws per stamp).
    @Test("matches an independently re-derived reference for a fixed input")
    func matchesIndependentReference() {
        let points = (0 ... 30).map { i in
            Point(x: 60 + Double(i) * 3.0, y: 200 + 14 * sin(Double(i) * 0.45))
        }
        let style = StampStrokeStyle(color: "#2d4a6b", strokeWidth: 12.0, opacity: 0.9)
        let stamps = computeStrokeStamps(points: points, style: style, brush: .oilRound)

        #expect(stamps.count == 41)

        func expectClose(_ a: Double, _ b: Double, tolerance: Double = 1e-4, _ label: String) {
            #expect(abs(a - b) < tolerance, "\(label): \(a) vs \(b)")
        }

        let first = stamps[0]
        expectClose(first.x, 60.000000, "first.x")
        expectClose(first.y, 200.000000, "first.y")
        expectClose(first.angle, 1.113046, "first.angle")
        expectClose(first.length, 7.779338, "first.length")
        expectClose(first.width, 5.519558, "first.width")
        expectClose(first.alpha, 0.626153, "first.alpha")
        #expect(first.variant == 0)
        #expect(first.color == Rgb(r: 40, g: 79, b: 115))

        let second = stamps[1]
        expectClose(second.x, 61.734624, "second.x")
        expectClose(second.y, 203.521008, "second.y")
        expectClose(second.alpha, 0.636225, "second.alpha")
        #expect(second.variant == 3)
        #expect(second.color == Rgb(r: 35, g: 62, b: 98))

        let last = stamps[stamps.count - 1]
        expectClose(last.x, 150.000000, "last.x")
        expectClose(last.y, 211.252982, "last.y")
        expectClose(last.alpha, 0.529380, "last.alpha")
        #expect(last.variant == 0)
        #expect(last.color == Rgb(r: 48, g: 69, b: 95))
    }

    @Test("stamp count grows roughly with stroke length")
    func stampCountScalesWithLength() {
        let style = StampStrokeStyle(color: "#000000", strokeWidth: 8, opacity: 1.0)
        let short = (0 ... 5).map { Point(x: Double($0) * 4, y: 0) }
        let long = (0 ... 5).map { Point(x: Double($0) * 40, y: 0) }
        let shortStamps = computeStrokeStamps(points: short, style: style, brush: nil)
        let longStamps = computeStrokeStamps(points: long, style: style, brush: nil)
        #expect(longStamps.count > shortStamps.count)
    }

    @Test("stamps are capped near MAX_STAMPS_PER_STROKE for very long strokes")
    func veryLongStrokeIsCapped() {
        let style = StampStrokeStyle(color: "#000000", strokeWidth: 8, opacity: 1.0)
        let points = (0 ... 200).map { Point(x: Double($0) * 500, y: 0) }
        let stamps = computeStrokeStamps(points: points, style: style, brush: nil)
        #expect(stamps.count <= 701)
    }
}

@Suite("generateSpriteAlpha")
struct SpriteAlphaTests {
    @Test("dimensions match SPRITE_BASE_WIDTH and the brush's aspect")
    func dimensions() {
        let sprite = generateSpriteAlpha(brush: .oilRound, variant: 0)
        #expect(sprite.height == spriteBaseWidth)
        let oilRoundDynamics = StampDynamics.dynamics(for: .oilRound)
        let expectedLength = max(8, Int((Double(spriteBaseWidth) * oilRoundDynamics.aspect).rounded()))
        #expect(sprite.width == expectedLength)
        #expect(sprite.data.count == sprite.width * sprite.height)
    }

    @Test("all texel values are within [0, 1]")
    func valuesAreUnitRange() {
        let sprite = generateSpriteAlpha(brush: .watercolor, variant: 2)
        for value in sprite.data {
            #expect(value >= 0 && value <= 1)
        }
    }

    @Test("deterministic per (brush, variant)")
    func deterministic() {
        let a = generateSpriteAlpha(brush: .dryBrush, variant: 1)
        let b = generateSpriteAlpha(brush: .dryBrush, variant: 1)
        #expect(a.data == b.data)
    }

    @Test("different variants of the same brush produce different textures")
    func variantsDiffer() {
        let a = generateSpriteAlpha(brush: .charcoal, variant: 0)
        let b = generateSpriteAlpha(brush: .charcoal, variant: 1)
        #expect(a.data != b.data)
    }

    @Test("nil brush falls back to the 'default' seed/dynamics, matching an explicit lookup miss")
    func nilBrushIsDefault() {
        let sprite = generateSpriteAlpha(brush: nil, variant: 0)
        #expect(sprite.height == spriteBaseWidth)
        let expectedLength = max(8, Int((Double(spriteBaseWidth) * StampDynamics.default.aspect).rounded()))
        #expect(sprite.width == expectedLength)
    }
}
