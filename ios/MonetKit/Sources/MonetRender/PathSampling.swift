import Foundation
import MonetProtocol

/// `samplePathPoints` (performer-render spec §3): turns a raw `Path`'s
/// control points into a flat, renderable point list. This is the
/// pixel-parity target sampler (not the server's raw-polyline raster path,
/// see spec §3's divergence note) — used for every completed-stroke render
/// pass, in both plotter freehand and paint-mode stamp resampling.
public enum PathSampling {
    public static func samplePoints(_ path: Path, maxSegmentLength: Double = 8, minCurveSegments: Int = 12) -> [Point] {
        guard path.type != .svg, !path.points.isEmpty else { return [] }
        switch path.type {
        case .line:
            guard path.points.count >= 2 else { return path.points }
            let p0 = path.points[0], p1 = path.points[1]
            let segments = max(1, Int((distance(p0, p1) / maxSegmentLength).rounded(.up)))
            return (0 ... segments).map { lerp(p0, p1, Double($0) / Double(segments)) }
        case .quadratic:
            guard path.points.count >= 3 else { return path.points }
            let p0 = path.points[0], p1 = path.points[1], p2 = path.points[2]
            let length = distance(p0, p1) + distance(p1, p2)
            let segments = max(minCurveSegments, Int((length / maxSegmentLength).rounded(.up)))
            return (0 ... segments).map { quadraticBezier(p0, p1, p2, Double($0) / Double(segments)) }
        case .cubic:
            guard path.points.count >= 4 else { return path.points }
            let p0 = path.points[0], p1 = path.points[1], p2 = path.points[2], p3 = path.points[3]
            let length = distance(p0, p1) + distance(p1, p2) + distance(p2, p3)
            let segments = max(minCurveSegments, Int((length / maxSegmentLength).rounded(.up)))
            return (0 ... segments).map { cubicBezier(p0, p1, p2, p3, Double($0) / Double(segments)) }
        case .polyline:
            return path.points
        case .svg:
            return []
        }
    }

    public static func distance(_ a: Point, _ b: Point) -> Double {
        ((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y)).squareRoot()
    }

    public static func lerp(_ a: Point, _ b: Point, _ t: Double) -> Point {
        Point(x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t)
    }

    public static func quadraticBezier(_ p0: Point, _ p1: Point, _ p2: Point, _ t: Double) -> Point {
        let mt = 1 - t
        let x = mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x
        let y = mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y
        return Point(x: x, y: y)
    }

    public static func cubicBezier(_ p0: Point, _ p1: Point, _ p2: Point, _ p3: Point, _ t: Double) -> Point {
        let mt = 1 - t
        let x = mt * mt * mt * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t * t * t * p3.x
        let y = mt * mt * mt * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t * t * t * p3.y
        return Point(x: x, y: y)
    }
}
