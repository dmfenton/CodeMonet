import CoreGraphics
import Foundation

/// `A`/`a` elliptical-arc-to-Bézier conversion (SVG 1.1 Appendix F.6),
/// split out of `SVGPath.swift` purely to keep that file a manageable size
/// — this is `SVGPathParser`'s arc handling, not a separate concern, hence
/// the plain `extension` rather than a standalone type.
extension SVGPathParser {
    /// The 5 numeric parameters an `A`/`a` command carries (bundled to keep
    /// `appendArc`/`centerParameterization` under SwiftLint's parameter-
    /// count limit).
    struct ArcParameters {
        var rx: Double
        var ry: Double
        var xAxisRotationDegrees: Double
        var largeArc: Bool
        var sweep: Bool
    }

    /// A fully-resolved elliptical arc in center parameterization, ready to
    /// walk from `theta1` through `theta1 + deltaTheta`.
    struct ArcCenter {
        var cx: Double
        var cy: Double
        var rx: Double
        var ry: Double
        var cosPhi: Double
        var sinPhi: Double
        var theta1: Double
        var deltaTheta: Double
    }

    /// Endpoint-to-center conversion (SVG 1.1 Appendix F.6.5). Returns
    /// `nil` for a degenerate arc (zero radius) — the caller falls back to
    /// a straight line, matching the spec's "correction" for an
    /// out-of-range radius pair.
    static func centerParameterization(from start: CGPoint, to end: CGPoint, parameters: ArcParameters) -> ArcCenter? {
        guard parameters.rx != 0, parameters.ry != 0 else { return nil }
        var rx = abs(parameters.rx)
        var ry = abs(parameters.ry)
        let phi = parameters.xAxisRotationDegrees * .pi / 180
        let cosPhi = cos(phi)
        let sinPhi = sin(phi)

        let dx2 = (start.x - end.x) / 2
        let dy2 = (start.y - end.y) / 2
        let x1p = cosPhi * dx2 + sinPhi * dy2
        let y1p = -sinPhi * dx2 + cosPhi * dy2

        let lambda = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
        if lambda > 1 {
            let scale = lambda.squareRoot()
            rx *= scale
            ry *= scale
        }

        let sign: Double = parameters.largeArc != parameters.sweep ? 1 : -1
        let num = max(0, rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p)
        let den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
        let coefficient = den == 0 ? 0 : sign * (num / den).squareRoot()
        let cxp = coefficient * (rx * y1p) / ry
        let cyp = coefficient * -(ry * x1p) / rx

        let cx = cosPhi * cxp - sinPhi * cyp + (start.x + end.x) / 2
        let cy = sinPhi * cxp + cosPhi * cyp + (start.y + end.y) / 2

        let theta1 = signedAngle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
        var deltaTheta = signedAngle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
        if !parameters.sweep, deltaTheta > 0 { deltaTheta -= 2 * .pi }
        if parameters.sweep, deltaTheta < 0 { deltaTheta += 2 * .pi }

        return ArcCenter(cx: cx, cy: cy, rx: rx, ry: ry, cosPhi: cosPhi, sinPhi: sinPhi, theta1: theta1, deltaTheta: deltaTheta)
    }

    /// Signed angle from vector `(ux,uy)` to vector `(vx,vy)`.
    static func signedAngle(_ ux: Double, _ uy: Double, _ vx: Double, _ vy: Double) -> Double {
        let dot = ux * vx + uy * vy
        let len = (ux * ux + uy * uy).squareRoot() * (vx * vx + vy * vy).squareRoot()
        var a = acos(max(-1, min(1, dot / len)))
        if ux * vy - uy * vx < 0 { a = -a }
        return a
    }

    /// Converts elliptical arc `(start, parameters, end)` into a short run
    /// of cubic Bézier segments (standard circle/ellipse-arc-to-Bézier
    /// approximation, one segment per <= 90° of sweep) appended to `path`.
    static func appendArc(to path: CGMutablePath, from start: CGPoint, parameters: ArcParameters, end: CGPoint) {
        guard start != end else { return }
        guard let center = centerParameterization(from: start, to: end, parameters: parameters) else {
            path.addLine(to: end)
            return
        }

        // Split into <= 90-degree segments for a good Bezier approximation.
        let segmentCount = max(1, Int(ceil(abs(center.deltaTheta) / (.pi / 2))))
        let segmentAngle = center.deltaTheta / Double(segmentCount)
        let alpha = sin(segmentAngle) * (4.0 / 3.0) * (sqrt(4 + 3 * pow(tan(segmentAngle / 2), 2)) - 1) / 3.0

        var theta = center.theta1
        for _ in 0 ..< segmentCount {
            let nextTheta = theta + segmentAngle
            let p0 = ellipsePoint(center, theta)
            let p3 = ellipsePoint(center, nextTheta)
            let t0 = ellipseTangent(center, theta)
            let t1 = ellipseTangent(center, nextTheta)
            let c1 = CGPoint(x: p0.x + alpha * t0.x, y: p0.y + alpha * t0.y)
            let c2 = CGPoint(x: p3.x - alpha * t1.x, y: p3.y - alpha * t1.y)
            path.addCurve(to: p3, control1: c1, control2: c2)
            theta = nextTheta
        }
    }

    static func ellipsePoint(_ center: ArcCenter, _ theta: Double) -> CGPoint {
        let ex = center.cx + center.rx * cos(theta) * center.cosPhi - center.ry * sin(theta) * center.sinPhi
        let ey = center.cy + center.rx * cos(theta) * center.sinPhi + center.ry * sin(theta) * center.cosPhi
        return CGPoint(x: ex, y: ey)
    }

    static func ellipseTangent(_ center: ArcCenter, _ theta: Double) -> CGPoint {
        let tx = -center.rx * sin(theta) * center.cosPhi - center.ry * cos(theta) * center.sinPhi
        let ty = -center.rx * sin(theta) * center.sinPhi + center.ry * cos(theta) * center.cosPhi
        return CGPoint(x: tx, y: ty)
    }
}
