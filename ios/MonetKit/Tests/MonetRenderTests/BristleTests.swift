@testable import MonetProtocol
@testable import MonetRender
import Testing

@Suite("getBristleOutlines")
struct BristleTests {
    @Test("produces one outline per bristle")
    func oneOutlinePerBristle() {
        let points = (0 ... 20).map { Point(x: Double($0) * 4, y: 0) }
        let options = FreehandPresets.from(preset: BrushPreset.preset(for: .oilRound), strokeWidth: 10)
        let bristles = getBristleOutlines(inputPoints: points, bristleCount: 3, spread: 5, options: options)
        #expect(bristles.count == 3)
        for outline in bristles { #expect(!outline.isEmpty) }
    }

    @Test("zero bristle count produces no outlines")
    func zeroCountIsEmpty() {
        let points = [Point(x: 0, y: 0), Point(x: 10, y: 0)]
        let options = FreehandPresets.painterlyDefault(size: 8)
        #expect(getBristleOutlines(inputPoints: points, bristleCount: 0, spread: 5, options: options).isEmpty)
    }

    @Test("empty input points produces no outlines")
    func emptyPointsIsEmpty() {
        let options = FreehandPresets.painterlyDefault(size: 8)
        #expect(getBristleOutlines(inputPoints: [], bristleCount: 4, spread: 5, options: options).isEmpty)
    }

    @Test("a single bristle has zero centerline offset")
    func singleBristleNoOffset() {
        // With bristleCount == 1 the spec's offset formula is 0 (no spread
        // fan), only the small per-point jitter remains.
        let points = (0 ... 10).map { Point(x: Double($0) * 10, y: 0) }
        let options = FreehandPresets.painterlyDefault(size: 8)
        let bristles = getBristleOutlines(inputPoints: points, bristleCount: 1, spread: 0, options: options)
        #expect(bristles.count == 1)
        // With spread=0 there's no jitter either, so this should match a
        // plain freehand outline of the same (unjittered) points at the
        // bristle size/thinning.
        var bristleOptions = options
        bristleOptions.size = options.size * 0.3
        bristleOptions.thinning = 0.3
        #expect(bristles[0] == getFreehandOutline(points, options: bristleOptions))
    }
}
