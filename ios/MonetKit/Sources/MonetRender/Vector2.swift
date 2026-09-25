import Foundation
import MonetProtocol

/// Minimal 2D vector math on `Point`, mirroring `perfect-freehand`'s `vec.ts`
/// (performer-render spec §4). Kept file-private to `MonetRender` — callers
/// use the higher-level `getFreehandOutline`/`computeStrokeStamps` APIs, not
/// these primitives directly.
enum Vec2 {
    static func add(_ a: Point, _ b: Point) -> Point {
        Point(x: a.x + b.x, y: a.y + b.y)
    }

    static func sub(_ a: Point, _ b: Point) -> Point {
        Point(x: a.x - b.x, y: a.y - b.y)
    }

    static func neg(_ a: Point) -> Point {
        Point(x: -a.x, y: -a.y)
    }

    static func mul(_ a: Point, _ n: Double) -> Point {
        Point(x: a.x * n, y: a.y * n)
    }

    /// Perpendicular rotation (`per`, `vec.ts:96-98`): `[y, -x]`.
    static func per(_ a: Point) -> Point {
        Point(x: a.y, y: -a.x)
    }

    /// Dot product (`dpr`).
    static func dot(_ a: Point, _ b: Point) -> Double {
        a.x * b.x + a.y * b.y
    }

    static func length(_ a: Point) -> Double {
        (a.x * a.x + a.y * a.y).squareRoot()
    }

    /// Normalized vector. Matches the JS reference's `div(A, len(A))`
    /// exactly, including its NaN/Infinity behavior for a zero vector.
    static func normalized(_ a: Point) -> Point {
        let l = length(a)
        return Point(x: a.x / l, y: a.y / l)
    }

    static func distance(_ a: Point, _ b: Point) -> Double {
        length(sub(a, b))
    }

    /// Squared distance (`dist2`) — used for the outline's minimum-distance
    /// gate, where the extra `sqrt` would be wasted work.
    static func distanceSquared(_ a: Point, _ b: Point) -> Double {
        let d = sub(a, b)
        return d.x * d.x + d.y * d.y
    }

    /// Linear interpolation from `a` to `b` by `t` (`lrp`).
    static func lerp(_ a: Point, _ b: Point, _ t: Double) -> Point {
        add(a, mul(sub(b, a), t))
    }

    /// Project `a` in direction `b` by scalar `c` (`prj`).
    static func project(_ a: Point, _ direction: Point, _ c: Double) -> Point {
        add(a, mul(direction, c))
    }

    /// Rotate `a` around center `c` by `r` radians (`rotAround`).
    static func rotate(_ a: Point, around c: Point, by r: Double) -> Point {
        let s = sin(r)
        let cosR = cos(r)
        let px = a.x - c.x
        let py = a.y - c.y
        let nx = px * cosR - py * s
        let ny = px * s + py * cosR
        return Point(x: nx + c.x, y: ny + c.y)
    }
}
