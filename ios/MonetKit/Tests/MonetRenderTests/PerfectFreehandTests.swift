@testable import MonetProtocol
@testable import MonetRender
import Testing

@Suite("FreehandPresets")
struct FreehandPresetsTests {
    @Test("painterlyDefault only overrides size (spec §4.6 quirk)")
    func painterlyDefaultQuirk() {
        let narrow = FreehandPresets.painterlyDefault(size: 2.5)
        let wide = FreehandPresets.painterlyDefault(size: 40)
        #expect(narrow.size == 2.5)
        #expect(wide.size == 40)
        // taper/thinning stay fixed regardless of the requested size.
        #expect(narrow.thinning == 0.6)
        #expect(wide.thinning == 0.6)
        if case let .amount(a) = narrow.start.taper, case let .amount(b) = wide.start.taper {
            #expect(a == 40)
            #expect(b == 40)
        } else {
            Issue.record("expected a fixed .amount(40) taper regardless of size")
        }
    }

    @Test("brush-preset options scale taper by the preset's fraction and stroke width")
    func brushPresetTaperScalesWithWidth() {
        let preset = BrushPreset.preset(for: .oilRound)
        let options = FreehandPresets.from(preset: preset, strokeWidth: 20)
        #expect(options.size == 20)
        #expect(options.thinning == preset.pressureResponse * 0.8)
        if case let .amount(taper) = options.start.taper {
            #expect(abs(taper - preset.taper * 20) < 1e-9)
        } else {
            Issue.record("expected an .amount taper")
        }
    }
}

@Suite("getFreehandOutline")
struct FreehandOutlineTests {
    @Test("empty input produces an empty outline")
    func emptyInput() {
        #expect(getFreehandOutline([], options: FreehandPresets.painterlyDefault(size: 8)).isEmpty)
    }

    @Test("a lone StrokePoint (untapered, not mid-completion) draws a closed dot polygon")
    func singleStrokePointDot() {
        // Exercises `getStrokeOutlinePoints`'s `drawDot` branch directly.
        // `getFreehandOutline`'s own `getStrokePoints` stage pads a single
        // *input* point to two StrokePoints before this runs (perfect-
        // freehand's actual, if slightly surprising, behavior — a genuinely
        // single-element StrokePoint list only arises from a caller that
        // builds one by hand), so this test targets the outline stage in
        // isolation rather than round-tripping through the padding.
        let strokePoint = FreehandStrokePoint(
            point: Point(x: 100, y: 100), pressure: 0.5, vector: Point(x: 1, y: 0), distance: 0, runningLength: 0
        )
        let options = FreehandOptions(size: 10, thinning: 0.5, smoothing: 0.5, streamline: 0.5, simulatePressure: true)
        let outline = getStrokeOutlinePoints([strokePoint], options: options)
        // drawDot walks a full turn in START_CAP_SEGMENTS(=13) steps.
        #expect(outline.count == 13)
        for p in outline {
            let d = ((p.x - 100) * (p.x - 100) + (p.y - 100) * (p.y - 100)).squareRoot()
            #expect(d > 0)
        }
    }

    @Test("a straight two-point stroke stays centered on its axis and heads the right direction")
    func straightStrokeStaysOnAxis() {
        let options = FreehandOptions(size: 10, thinning: 0.5, smoothing: 0.5, streamline: 0.5, simulatePressure: true)
        let outline = getFreehandOutline([Point(x: 0, y: 0), Point(x: 200, y: 0)], options: options)
        #expect(!outline.isEmpty)
        // The outline should be roughly bounded around the segment: no
        // point should stray more than a couple of stroke-widths off axis.
        let maxY = outline.map { abs($0.y) }.max() ?? 0
        #expect(maxY < 20)
        // perfect-freehand's streamline smoothing makes the visible stroke
        // lag behind the raw input (a well-known, intentional library
        // characteristic, not a bug) — it starts at the origin and heads
        // substantially toward the target without needing to reach it
        // exactly for an incomplete (`last: false`) stroke.
        let minX = outline.map(\.x).min() ?? 0
        let maxX = outline.map(\.x).max() ?? 0
        #expect(minX < 5)
        #expect(maxX > 140)
    }

    @Test("size <= 0 produces an empty outline")
    func nonPositiveSizeIsEmpty() {
        let options = FreehandOptions(size: 0, thinning: 0.5, smoothing: 0.5, streamline: 0.5, simulatePressure: true)
        #expect(getFreehandOutline([Point(x: 0, y: 0), Point(x: 10, y: 10)], options: options).isEmpty)
    }

    @Test("deterministic for identical input (no hidden randomness)")
    func deterministicOutput() {
        let points = [Point(x: 0, y: 0), Point(x: 40, y: 10), Point(x: 90, y: -5), Point(x: 140, y: 20)]
        let options = FreehandPresets.painterlyDefault(size: 12)
        let a = getFreehandOutline(points, options: options)
        let b = getFreehandOutline(points, options: options)
        #expect(a == b)
    }

    @Test("a tapered stroke narrows toward both ends vs an untapered one")
    func taperNarrowsEnds() {
        let points = (0 ... 40).map { Point(x: Double($0) * 5, y: 0) }
        let untapered = FreehandOptions(size: 16, thinning: 0.5, smoothing: 0.5, streamline: 0.5, simulatePressure: true)
        var tapered = untapered
        tapered.start = FreehandCapOptions(cap: true, taper: .amount(60), easing: FreehandEasing.quadratic)
        tapered.end = FreehandCapOptions(cap: true, taper: .amount(60), easing: FreehandEasing.quadratic)

        let untaperedOutline = getFreehandOutline(points, options: untapered)
        let taperedOutline = getFreehandOutline(points, options: tapered)

        // The tapered stroke's start cap collapses to (near) the first
        // point rather than fanning out into a full round cap.
        let untaperedSpreadNearStart = untaperedOutline
            .filter { $0.x < 15 }
            .map { abs($0.y) }
            .max() ?? 0
        let taperedSpreadNearStart = taperedOutline
            .filter { $0.x < 15 }
            .map { abs($0.y) }
            .max() ?? 0
        #expect(taperedSpreadNearStart < untaperedSpreadNearStart)
    }
}

@Suite("applyVelocityPressure")
struct VelocityPressureTests {
    // `pressureFactor = clamp(1 / (1 + avgDist*0.015), 0.6, 1.2)`
    // (`shared/src/utils/velocityPressure.ts`): for any non-negative
    // avgDist this is in `(0, 1]`, approaching 1 (not 1.2) as avgDist -> 0
    // — the 1.2 upper clamp is unreachable by this formula. Slower movement
    // still ends up *relatively* thicker than faster movement, it just
    // never exceeds the base size.
    @Test("slower movement stays closer to the base size than faster movement, both floored at 0.6x")
    func velocityScalesSize() {
        let base = FreehandOptions(size: 10, thinning: 0.5, smoothing: 0.5, streamline: 0.5, simulatePressure: true)
        let slow = [Point(x: 0, y: 0), Point(x: 1, y: 0), Point(x: 2, y: 0)]
        let fast = [Point(x: 0, y: 0), Point(x: 500, y: 0), Point(x: 1000, y: 0)]

        let slowOptions = applyVelocityPressure(points: slow, options: base, fallbackSize: 10)
        let fastOptions = applyVelocityPressure(points: fast, options: base, fallbackSize: 10)

        #expect(slowOptions.size <= base.size + 1e-9)
        #expect(slowOptions.size > fastOptions.size)
        #expect(fastOptions.size >= base.size * 0.6 - 1e-9)
    }

    @Test("fewer than 2 points returns options unchanged")
    func tooFewPointsIsNoop() {
        let base = FreehandOptions(size: 10, thinning: 0.5, smoothing: 0.5, streamline: 0.5, simulatePressure: true)
        let result = applyVelocityPressure(points: [Point(x: 0, y: 0)], options: base, fallbackSize: 10)
        #expect(result.size == base.size)
    }
}
