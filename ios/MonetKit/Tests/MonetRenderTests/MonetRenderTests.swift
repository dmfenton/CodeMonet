@testable import MonetProtocol
@testable import MonetRender
import Testing

@Suite("Mulberry32")
struct Mulberry32Tests {
    @Test("is deterministic for a fixed seed")
    func deterministic() {
        var a = Mulberry32(seed: 42)
        var b = Mulberry32(seed: 42)
        for _ in 0 ..< 20 {
            #expect(a.next() == b.next())
        }
    }

    @Test("produces values in [0, 1)")
    func rangeIsUnitInterval() {
        var rng = Mulberry32(seed: 1)
        for _ in 0 ..< 1000 {
            let value = rng.next()
            #expect(value >= 0 && value < 1)
        }
    }

    @Test("different seeds diverge")
    func differentSeedsDiverge() {
        var a = Mulberry32(seed: 1)
        var b = Mulberry32(seed: 2)
        #expect(a.next() != b.next())
    }
}

@Suite("PathSampling")
struct PathSamplingTests {
    @Test("line with 2 points samples endpoints")
    func lineSamplesEndpoints() {
        let path = Path(type: .line, points: [Point(x: 0, y: 0), Point(x: 10, y: 0)])
        let points = PathSampling.samplePoints(path)
        #expect(points.first == Point(x: 0, y: 0))
        #expect(points.last == Point(x: 10, y: 0))
    }

    @Test("polyline is not resampled")
    func polylineUnchanged() {
        let raw = [Point(x: 0, y: 0), Point(x: 5, y: 5), Point(x: 10, y: 0)]
        let path = Path(type: .polyline, points: raw)
        #expect(PathSampling.samplePoints(path) == raw)
    }

    @Test("svg path samples to empty")
    func svgSamplesEmpty() {
        let path = Path(type: .svg, points: [], d: "M0 0 L10 10")
        #expect(PathSampling.samplePoints(path).isEmpty)
    }
}

@Suite("StampDynamics/BrushPreset tables")
struct DataTableTests {
    @Test("every BrushName has a stamp-dynamics entry")
    func stampDynamicsCoversAllBrushes() {
        for brush in BrushName.allCases {
            #expect(StampDynamics.table[brush] != nil)
        }
    }

    @Test("every BrushName has a brush-preset entry")
    func brushPresetCoversAllBrushes() {
        for brush in BrushName.allCases {
            #expect(BrushPreset.table[brush] != nil)
        }
    }
}
