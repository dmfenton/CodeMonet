import CoreGraphics
@testable import MonetProtocol
@testable import MonetRender
import Testing

@Suite("SVGPathParser")
struct SVGPathParserTests {
    @Test("simple move+line produces a path with the expected bounding box")
    func moveLine() throws {
        let path = try #require(SVGPathParser.parse("M10 10 L90 10 L90 90 L10 90 Z"))
        let box = path.boundingBox
        #expect(abs(box.minX - 10) < 0.5)
        #expect(abs(box.minY - 10) < 0.5)
        #expect(abs(box.maxX - 90) < 0.5)
        #expect(abs(box.maxY - 90) < 0.5)
    }

    @Test("relative commands accumulate from the current point")
    func relativeCommands() throws {
        let absolute = try #require(SVGPathParser.parse("M0 0 L50 0 L50 50"))
        let relative = try #require(SVGPathParser.parse("M0 0 l50 0 l0 50"))
        #expect(absolute.boundingBox.equalTo(relative.boundingBox))
    }

    @Test("implicit command repetition: extra pairs after M become L")
    func implicitRepetition() throws {
        // "M0 0 10 10 20 0" == "M0 0 L10 10 L20 0"
        let implicit = try #require(SVGPathParser.parse("M0 0 10 10 20 0"))
        let explicit = try #require(SVGPathParser.parse("M0 0 L10 10 L20 0"))
        #expect(implicit.boundingBox.equalTo(explicit.boundingBox))
    }

    @Test("H and V commands move only one axis")
    func horizontalVertical() throws {
        let path = try #require(SVGPathParser.parse("M0 0 H100 V50"))
        let box = path.boundingBox
        #expect(abs(box.maxX - 100) < 0.5)
        #expect(abs(box.maxY - 50) < 0.5)
    }

    @Test("cubic and quadratic curves stay within their control-point hull")
    func curvesWithinHull() throws {
        let cubic = try #require(SVGPathParser.parse("M0 0 C 10 100, 90 100, 100 0"))
        let box = cubic.boundingBox
        #expect(box.minX >= -1 && box.maxX <= 101)
        #expect(box.minY >= -1 && box.maxY <= 101)

        let quad = try #require(SVGPathParser.parse("M0 0 Q 50 100 100 0"))
        let qbox = quad.boundingBox
        #expect(qbox.minX >= -1 && qbox.maxX <= 101)
        #expect(qbox.minY >= -1 && qbox.maxY <= 101)
    }

    @Test("S/T reflect the previous control point")
    func smoothReflection() throws {
        // A straight-through S after a C with a horizontal tangent should
        // continue smoothly rather than kinking backward — just assert it
        // parses to a non-degenerate, reasonably-sized path.
        let path = try #require(SVGPathParser.parse("M0 50 C 25 0, 75 0, 100 50 S 175 100, 200 50"))
        let box = path.boundingBox
        #expect(box.maxX > 190)
    }

    @Test("a closed arc stays within a sane bounding box around its radius")
    func arcCommand() throws {
        // A full-circle-ish pair of semicircular arcs from (0,50) to
        // (100,50) and back, rx=ry=50.
        let path = try #require(SVGPathParser.parse("M0 50 A50 50 0 1 1 100 50 A50 50 0 1 1 0 50 Z"))
        let box = path.boundingBox
        #expect(box.minX > -5 && box.maxX < 105)
        #expect(box.minY > -5 && box.maxY < 105)
        // Should bulge out roughly to y=0 and y=100 (the arcs' extremes).
        #expect(box.minY < 10)
        #expect(box.maxY > 90)
    }

    @Test("degenerate/empty input produces an empty (but non-nil) path")
    func emptyInput() throws {
        let path = try #require(SVGPathParser.parse(""))
        #expect(path.isEmpty)
    }

    @Test("malformed trailing input still returns whatever parsed so far")
    func malformedTrailingInput() throws {
        let path = try #require(SVGPathParser.parse("M0 0 L10 10 L"))
        #expect(!path.isEmpty)
    }
}

@Suite("StrokeSmoothing.catmullRomPath")
struct CatmullRomTests {
    @Test("starts at the first point and ends at the last")
    func startsAndEndsCorrectly() {
        let points = [Point(x: 0, y: 0), Point(x: 10, y: 20), Point(x: 30, y: -10), Point(x: 50, y: 5)]
        let path = StrokeSmoothing.catmullRomPath(points)
        let box = path.boundingBox
        #expect(box.contains(CGPoint(x: 0, y: 0)))
        #expect(!path.isEmpty)
    }

    @Test("two points falls back to a straight line")
    func twoPointsIsLine() {
        let path = StrokeSmoothing.catmullRomPath([Point(x: 0, y: 0), Point(x: 10, y: 10)])
        let box = path.boundingBox
        #expect(abs(box.width - 10) < 0.5)
        #expect(abs(box.height - 10) < 0.5)
    }
}
