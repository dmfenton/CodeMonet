import Foundation
import MonetProtocol

/// `getStrokeOutlinePoints` (performer-render spec §4.5) and its supporting
/// cap/corner-fan geometry — split out of `PerfectFreehand.swift` (which
/// keeps the shared types, constants, and `getStrokePoints`) purely to keep
/// each file a manageable size; this is one continuous algorithm with that
/// file, not a separate concern.

private func computeTaperDistance(_ taper: FreehandCapOptions.Taper, size: Double, totalLength: Double) -> Double {
    switch taper {
    case .off: return 0
    case .full: return max(size, totalLength)
    case let .amount(value): return value
    }
}

private func computeInitialPressure(points: [FreehandStrokePoint], simulatePressure: Bool, size: Double) -> Double {
    var acc = points[0].pressure
    for p in points.prefix(10) {
        let pressure = simulatePressure ? simulatedPressure(prevPressure: acc, distance: p.distance, size: size) : p.pressure
        acc = (acc + pressure) / 2
    }
    return acc
}

private func drawDot(center: Point, radius: Double) -> [Point] {
    let offsetPoint = Vec2.add(center, Point(x: 1, y: 1))
    let start = Vec2.project(center, Vec2.normalized(Vec2.per(Vec2.sub(center, offsetPoint))), -radius)
    var pts: [Point] = []
    let step = 1.0 / Double(FreehandConstants.startCapSegments)
    var t = step
    while t <= 1 {
        pts.append(Vec2.rotate(start, around: center, by: FreehandConstants.fixedPi * 2 * t))
        t += step
    }
    return pts
}

private func drawRoundStartCap(center: Point, rightPoint: Point, segments: Int) -> [Point] {
    var cap: [Point] = []
    let step = 1.0 / Double(segments)
    var t = step
    while t <= 1 {
        cap.append(Vec2.rotate(rightPoint, around: center, by: FreehandConstants.fixedPi * t))
        t += step
    }
    return cap
}

private func drawFlatStartCap(center: Point, leftPoint: Point, rightPoint: Point) -> [Point] {
    let cornersVector = Vec2.sub(leftPoint, rightPoint)
    let offsetA = Vec2.mul(cornersVector, 0.5)
    let offsetB = Vec2.mul(cornersVector, 0.51)
    return [Vec2.sub(center, offsetA), Vec2.sub(center, offsetB), Vec2.add(center, offsetB), Vec2.add(center, offsetA)]
}

private func drawRoundEndCap(center: Point, direction: Point, radius: Double, segments: Int) -> [Point] {
    var cap: [Point] = []
    let start = Vec2.project(center, direction, radius)
    let step = 1.0 / Double(segments)
    var t = step
    while t < 1 {
        cap.append(Vec2.rotate(start, around: center, by: FreehandConstants.fixedPi * 3 * t))
        t += step
    }
    return cap
}

private func drawFlatEndCap(center: Point, direction: Point, radius: Double) -> [Point] {
    [
        Vec2.add(center, Vec2.mul(direction, radius)),
        Vec2.add(center, Vec2.mul(direction, radius * 0.99)),
        Vec2.sub(center, Vec2.mul(direction, radius * 0.99)),
        Vec2.sub(center, Vec2.mul(direction, radius)),
    ]
}

/// The stroke's total arc length plus its resolved start/end taper
/// distances (spec §4.5) — computed once before the outline walk, then
/// threaded through per-point radius resolution.
private struct TaperDistances {
    var start: Double
    var end: Double
    var totalLength: Double

    init(totalLength: Double, options: FreehandOptions) {
        self.totalLength = totalLength
        start = computeTaperDistance(options.start.taper, size: options.size, totalLength: totalLength)
        end = computeTaperDistance(options.end.taper, size: options.size, totalLength: totalLength)
    }
}

/// Per-point (radius, pressure) after (simulated) pressure and start/end
/// taper easing — the spec §4.5 block that runs once per surviving point,
/// factored out so the main outline walk reads as a sequence of named steps
/// rather than one long function.
private func resolvedRadiusAndPressure(
    for point: FreehandStrokePoint, prevPressure: Double, options: FreehandOptions, taper: TaperDistances
) -> (radius: Double, pressure: Double) {
    var pressure = point.pressure
    var radius: Double
    if options.thinning != 0 {
        if options.simulatePressure {
            pressure = simulatedPressure(prevPressure: prevPressure, distance: point.distance, size: options.size)
        }
        radius = strokeRadius(size: options.size, thinning: options.thinning, pressure: pressure, easing: options.easing)
    } else {
        radius = options.size / 2
    }

    let runningLength = point.runningLength
    let startStrength = runningLength < taper.start ? options.start.easing(runningLength / taper.start) : 1
    let remaining = taper.totalLength - runningLength
    let endStrength = remaining < taper.end ? options.end.easing(remaining / taper.end) : 1
    radius = max(FreehandConstants.minRadius, radius * min(startStrength, endStrength))
    return (radius, pressure)
}

/// Fans a `CORNER_CAP_SEGMENTS`-step semicircle on both sides of a sharp
/// corner (spec §4.5's sharp-corner branch).
private func cornerFan(around point: Point, prevVector: Point, radius: Double) -> (left: [Point], right: [Point]) {
    let offset = Vec2.mul(Vec2.per(prevVector), radius)
    var left: [Point] = []
    var right: [Point] = []
    var t = 0.0
    let step = 1.0 / Double(FreehandConstants.cornerCapSegments)
    while t <= 1 {
        left.append(Vec2.rotate(Vec2.sub(point, offset), around: point, by: FreehandConstants.fixedPi * t))
        right.append(Vec2.rotate(Vec2.add(point, offset), around: point, by: FreehandConstants.fixedPi * -t))
        t += step
    }
    return (left, right)
}

/// Accumulates the outline's left/right point sequences (spec §4.5's
/// `leftPts`/`rightPts` plus the "previous pushed point" state the minimum-
/// distance gate needs) — factored out so `getStrokeOutlinePoints`'s main
/// walk reads as a sequence of named steps.
private struct OutlineSides {
    var left: [Point] = []
    var right: [Point] = []
    private var prevLeft: Point
    private var prevRight: Point

    init(start: Point) {
        prevLeft = start
        prevRight = start
    }

    mutating func appendCornerFan(around point: Point, prevVector: Point, radius: Double) {
        let fan = cornerFan(around: point, prevVector: prevVector, radius: radius)
        left.append(contentsOf: fan.left)
        right.append(contentsOf: fan.right)
        prevLeft = fan.left.last ?? prevLeft
        prevRight = fan.right.last ?? prevRight
    }

    mutating func appendEndpoint(_ point: Point, offset: Point) {
        left.append(Vec2.sub(point, offset))
        right.append(Vec2.add(point, offset))
    }

    /// Regular (non-corner, non-endpoint) point: only pushed once it's
    /// moved at least `sqrt(minDistance)` from the last pushed point on
    /// that side — except the first couple of points (`force`), which are
    /// always kept (spec §4.5's `i <= 1` escape hatch).
    mutating func appendRegular(_ point: Point, offset: Point, minDistance: Double, force: Bool) {
        let candidateLeft = Vec2.sub(point, offset)
        if force || Vec2.distanceSquared(prevLeft, candidateLeft) > minDistance {
            left.append(candidateLeft)
            prevLeft = candidateLeft
        }
        let candidateRight = Vec2.add(point, offset)
        if force || Vec2.distanceSquared(prevRight, candidateRight) > minDistance {
            right.append(candidateRight)
            prevRight = candidateRight
        }
    }
}

/// `getStrokeOutlinePoints` (spec §4.5): walk the resampled points, compute
/// a per-point radius from (simulated) pressure, offset left/right, and
/// close the polygon with caps or tapers. Returns a single closed polygon in
/// winding order left -> end cap -> right (reversed) -> start cap.
func getStrokeOutlinePoints(_ points: [FreehandStrokePoint], options: FreehandOptions) -> [Point] {
    guard !points.isEmpty, options.size > 0 else { return [] }

    let totalLength = points[points.count - 1].runningLength
    let taper = TaperDistances(totalLength: totalLength, options: options)
    let minDistance = pow(options.size * options.smoothing, 2)

    var sides = OutlineSides(start: points[0].point)

    var prevPressure = computeInitialPressure(points: points, simulatePressure: options.simulatePressure, size: options.size)
    let lastPressure = points[points.count - 1].pressure
    var radius = strokeRadius(size: options.size, thinning: options.thinning, pressure: lastPressure, easing: options.easing)
    var firstRadius: Double?
    var prevVector = points[0].vector
    var isPrevPointSharpCorner = false

    for i in 0 ..< points.count {
        let point = points[i].point
        let vector = points[i].vector
        let runningLength = points[i].runningLength
        let isLastPoint = i == points.count - 1

        if !isLastPoint, (totalLength - runningLength) < FreehandConstants.endNoiseThreshold { continue }

        let resolved = resolvedRadiusAndPressure(for: points[i], prevPressure: prevPressure, options: options, taper: taper)
        radius = resolved.radius
        if firstRadius == nil { firstRadius = radius }

        let nextVector = isLastPoint ? vector : points[i + 1].vector
        let nextDot = isLastPoint ? 1.0 : Vec2.dot(vector, nextVector)
        let prevDot = Vec2.dot(vector, prevVector)
        let isSharpCorner = prevDot < 0 && !isPrevPointSharpCorner
        let isNextSharpCorner = nextDot < 0

        if isSharpCorner || isNextSharpCorner {
            sides.appendCornerFan(around: point, prevVector: prevVector, radius: radius)
            if isNextSharpCorner { isPrevPointSharpCorner = true }
            continue
        }
        isPrevPointSharpCorner = false

        if isLastPoint {
            sides.appendEndpoint(point, offset: Vec2.mul(Vec2.per(vector), radius))
            continue
        }

        let blended = Vec2.lerp(nextVector, vector, nextDot)
        sides.appendRegular(point, offset: Vec2.mul(Vec2.per(blended), radius), minDistance: minDistance, force: i <= 1)

        prevPressure = resolved.pressure
        prevVector = vector
    }

    let firstPoint = points[0].point
    let lastPoint = points.count > 1 ? points[points.count - 1].point : Vec2.add(points[0].point, Point(x: 1, y: 1))

    if points.count == 1 {
        if (!taper.start.isNonZero() && !taper.end.isNonZero()) || options.last {
            return drawDot(center: firstPoint, radius: firstRadius ?? radius)
        }
        // Tapered, incomplete single-point stroke: no caps are drawn (matches
        // the JS reference, which falls through with empty start/end caps).
        return sides.left + sides.right.reversed()
    }

    let startCap = startCap(firstPoint: firstPoint, sides: sides, taper: taper, options: options)
    let lastVector = points[points.count - 1].vector
    let endCap = endCap(lastPoint: lastPoint, lastVector: lastVector, radius: radius, taper: taper, options: options)

    return sides.left + endCap + sides.right.reversed() + startCap
}

private func startCap(firstPoint: Point, sides: OutlineSides, taper: TaperDistances, options: FreehandOptions) -> [Point] {
    if taper.start.isNonZero() {
        return [] // Tapered start: no cap.
    } else if options.start.cap {
        return drawRoundStartCap(center: firstPoint, rightPoint: sides.right[0], segments: FreehandConstants.startCapSegments)
    } else {
        return drawFlatStartCap(center: firstPoint, leftPoint: sides.left[0], rightPoint: sides.right[0])
    }
}

private func endCap(lastPoint: Point, lastVector: Point, radius: Double, taper: TaperDistances, options: FreehandOptions) -> [Point] {
    let direction = Vec2.per(Vec2.neg(lastVector))
    if taper.end.isNonZero() {
        return [lastPoint]
    } else if options.end.cap {
        return drawRoundEndCap(center: lastPoint, direction: direction, radius: radius, segments: FreehandConstants.endCapSegments)
    } else {
        return drawFlatEndCap(center: lastPoint, direction: direction, radius: radius)
    }
}

private extension Double {
    func isNonZero() -> Bool { self != 0 }
}

/// `getFreehandOutline` (spec §4, top-level entry point): resample +
/// outline in one call.
public func getFreehandOutline(_ inputPoints: [Point], options: FreehandOptions) -> [Point] {
    guard !inputPoints.isEmpty else { return [] }
    return getStrokeOutlinePoints(getStrokePoints(inputPoints, options: options), options: options)
}
