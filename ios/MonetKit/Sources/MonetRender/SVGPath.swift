import CoreGraphics
import Foundation
import MonetProtocol

/// Parses an SVG path `d` string into a `CGPath` (performer-render spec
/// §8.2): `type == .svg` paths skip point-sampling entirely and are handed
/// to a real vector-path parser on both the TS client (`Skia.Path.
/// MakeFromSVGString`) and here. Supports the full command set the spec
/// calls out: `M/m L/l H/h V/v C/c S/s Q/q T/t A/a Z/z`, relative and
/// absolute, with SVG's implicit-command-repetition grammar (extra
/// coordinate groups after a command letter reuse that command; extra pairs
/// after `M`/`m` become implicit `L`/`l`).
enum SVGPathParser {
    static func parse(_ d: String) -> CGPath? {
        var scanner = Scanner(d)
        let builder = SVGPathBuilder()

        while let commandChar = scanner.nextCommandLetter() {
            let isRelative = commandChar.isLowercase
            // `m`/`M`'s first coordinate pair moves; every trailing pair in
            // the same command is an implicit `l`/`L` — exactly the SVG
            // grammar's own equivalence, so switching the effective command
            // after the first op needs no special-casing per iteration.
            var command = Character(commandChar.lowercased())

            argumentLoop: while true {
                guard builder.apply(command: command, scanner: &scanner, isRelative: isRelative) else {
                    return builder.finish()
                }
                if command == "m" { command = "l" }
                if command == "z" || scanner.isAtEnd || scanner.peekIsCommandLetter() { break argumentLoop }
            }
        }

        return builder.finish()
    }

    /// Reflection of `point` through `center` — the implicit control point
    /// for `S`/`T` per the SVG spec (`2*current - lastControl`).
    fileprivate static func reflect(_ point: CGPoint, around center: CGPoint) -> CGPoint {
        CGPoint(x: 2 * center.x - point.x, y: 2 * center.y - point.y)
    }

    /// Mutable parse state (current point, subpath start, last cubic/quad
    /// control point for `S`/`T` reflection) plus one small method per SVG
    /// command — factored out of `parse` so each command's grammar reads as
    /// its own short function instead of one long `switch`.
    private final class SVGPathBuilder {
        private let path = CGMutablePath()
        private var current = CGPoint.zero
        private var subpathStart = CGPoint.zero
        private var lastCubicControl: CGPoint?
        private var lastQuadControl: CGPoint?
        private var hasSubpath = false

        func finish() -> CGPath { path.copy() ?? path }

        /// Applies one command's next argument group. Returns `false` when
        /// the input ran out of numbers mid-command or the command letter
        /// is unrecognized — the caller stops parsing and returns whatever
        /// built so far.
        func apply(command: Character, scanner: inout Scanner, isRelative: Bool) -> Bool {
            switch command {
            case "m": return moveTo(&scanner, isRelative: isRelative)
            case "l": return lineTo(&scanner, isRelative: isRelative)
            case "h": return horizontalLineTo(&scanner, isRelative: isRelative)
            case "v": return verticalLineTo(&scanner, isRelative: isRelative)
            case "c": return cubicCurveTo(&scanner, isRelative: isRelative)
            case "s": return smoothCubicCurveTo(&scanner, isRelative: isRelative)
            case "q": return quadCurveTo(&scanner, isRelative: isRelative)
            case "t": return smoothQuadCurveTo(&scanner, isRelative: isRelative)
            case "a": return arcTo(&scanner, isRelative: isRelative)
            case "z": closePath(); return true
            default: return false
            }
        }

        private func resolved(_ x: Double, _ y: Double, isRelative: Bool) -> CGPoint {
            isRelative ? CGPoint(x: current.x + x, y: current.y + y) : CGPoint(x: x, y: y)
        }

        private func clearReflectionControls() {
            lastCubicControl = nil
            lastQuadControl = nil
        }

        private func moveTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let x = scanner.nextNumber(), let y = scanner.nextNumber() else { return false }
            let p = resolved(x, y, isRelative: isRelative)
            path.move(to: p)
            subpathStart = p
            hasSubpath = true
            current = p
            clearReflectionControls()
            return true
        }

        private func lineTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let x = scanner.nextNumber(), let y = scanner.nextNumber() else { return false }
            let p = resolved(x, y, isRelative: isRelative)
            path.addLine(to: p)
            current = p
            clearReflectionControls()
            return true
        }

        private func horizontalLineTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let x = scanner.nextNumber() else { return false }
            let p = CGPoint(x: isRelative ? current.x + x : x, y: current.y)
            path.addLine(to: p)
            current = p
            clearReflectionControls()
            return true
        }

        private func verticalLineTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let y = scanner.nextNumber() else { return false }
            let p = CGPoint(x: current.x, y: isRelative ? current.y + y : y)
            path.addLine(to: p)
            current = p
            clearReflectionControls()
            return true
        }

        private func cubicCurveTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let x1 = scanner.nextNumber(), let y1 = scanner.nextNumber(),
                  let x2 = scanner.nextNumber(), let y2 = scanner.nextNumber(),
                  let x = scanner.nextNumber(), let y = scanner.nextNumber()
            else { return false }
            let c1 = resolved(x1, y1, isRelative: isRelative)
            let c2 = resolved(x2, y2, isRelative: isRelative)
            let p = resolved(x, y, isRelative: isRelative)
            path.addCurve(to: p, control1: c1, control2: c2)
            current = p
            lastCubicControl = c2
            lastQuadControl = nil
            return true
        }

        private func smoothCubicCurveTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let x2 = scanner.nextNumber(), let y2 = scanner.nextNumber(),
                  let x = scanner.nextNumber(), let y = scanner.nextNumber()
            else { return false }
            let c1 = lastCubicControl.map { SVGPathParser.reflect($0, around: current) } ?? current
            let c2 = resolved(x2, y2, isRelative: isRelative)
            let p = resolved(x, y, isRelative: isRelative)
            path.addCurve(to: p, control1: c1, control2: c2)
            current = p
            lastCubicControl = c2
            lastQuadControl = nil
            return true
        }

        private func quadCurveTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let x1 = scanner.nextNumber(), let y1 = scanner.nextNumber(),
                  let x = scanner.nextNumber(), let y = scanner.nextNumber()
            else { return false }
            let c1 = resolved(x1, y1, isRelative: isRelative)
            let p = resolved(x, y, isRelative: isRelative)
            path.addQuadCurve(to: p, control: c1)
            current = p
            lastQuadControl = c1
            lastCubicControl = nil
            return true
        }

        private func smoothQuadCurveTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let x = scanner.nextNumber(), let y = scanner.nextNumber() else { return false }
            let c1 = lastQuadControl.map { SVGPathParser.reflect($0, around: current) } ?? current
            let p = resolved(x, y, isRelative: isRelative)
            path.addQuadCurve(to: p, control: c1)
            current = p
            lastQuadControl = c1
            lastCubicControl = nil
            return true
        }

        private func arcTo(_ scanner: inout Scanner, isRelative: Bool) -> Bool {
            guard let rx = scanner.nextNumber(), let ry = scanner.nextNumber(),
                  let rotation = scanner.nextNumber(),
                  let largeArc = scanner.nextFlag(), let sweep = scanner.nextFlag(),
                  let x = scanner.nextNumber(), let y = scanner.nextNumber()
            else { return false }
            let p = resolved(x, y, isRelative: isRelative)
            let parameters = ArcParameters(rx: rx, ry: ry, xAxisRotationDegrees: rotation, largeArc: largeArc != 0, sweep: sweep != 0)
            appendArc(to: path, from: current, parameters: parameters, end: p)
            current = p
            clearReflectionControls()
            return true
        }

        private func closePath() {
            if hasSubpath { path.closeSubpath() }
            current = subpathStart
            clearReflectionControls()
        }
    }

    /// Minimal SVG path-data scanner: whitespace/comma separators, signed
    /// decimals with optional exponent, and single-digit arc flags (which
    /// may appear packed with no separator, e.g. `...0011...`).
    private struct Scanner {
        private let chars: [Character]
        private var index = 0
        private static let commandLetters = Set("MmLlHhVvCcSsQqTtAaZz")

        init(_ s: String) { chars = Array(s) }

        private mutating func skipSeparators() {
            while index < chars.count, chars[index] == " " || chars[index] == "," || chars[index] == "\n"
                || chars[index] == "\t" || chars[index] == "\r"
            { index += 1 }
        }

        var isAtEnd: Bool {
            mutating get {
                skipSeparators()
                return index >= chars.count
            }
        }

        mutating func peekIsCommandLetter() -> Bool {
            skipSeparators()
            guard index < chars.count else { return false }
            return Self.commandLetters.contains(chars[index])
        }

        mutating func nextCommandLetter() -> Character? {
            skipSeparators()
            guard index < chars.count, Self.commandLetters.contains(chars[index]) else { return nil }
            let c = chars[index]
            index += 1
            return c
        }

        mutating func nextNumber() -> Double? {
            skipSeparators()
            guard index < chars.count else { return nil }
            var i = index
            var s = ""
            if chars[i] == "+" || chars[i] == "-" { s.append(chars[i]); i += 1 }
            var sawDigit = false
            while i < chars.count, chars[i].isASCII, chars[i].isNumber { s.append(chars[i]); i += 1; sawDigit = true }
            if i < chars.count, chars[i] == "." {
                s.append("."); i += 1
                while i < chars.count, chars[i].isASCII, chars[i].isNumber { s.append(chars[i]); i += 1; sawDigit = true }
            }
            guard sawDigit else { return nil }
            if i < chars.count, chars[i] == "e" || chars[i] == "E" {
                var j = i + 1
                var exp = "e"
                if j < chars.count, chars[j] == "+" || chars[j] == "-" { exp.append(chars[j]); j += 1 }
                var sawExpDigit = false
                while j < chars.count, chars[j].isASCII, chars[j].isNumber { exp.append(chars[j]); j += 1; sawExpDigit = true }
                if sawExpDigit { s += exp; i = j }
            }
            index = i
            return Double(s)
        }

        /// Arc flag: a bare `0`/`1` digit, consumed as a single character so
        /// packed flags (`...11...`) still parse.
        mutating func nextFlag() -> Double? {
            skipSeparators()
            guard index < chars.count else { return nil }
            let c = chars[index]
            if c == "0" || c == "1" {
                index += 1
                return c == "0" ? 0 : 1
            }
            return nextNumber()
        }
    }
}

/// `smoothPolylineToPath`/`pathToSvgD`'s Catmull-Rom smoothing (spec §8.4),
/// built directly as a `CGPath` rather than an SVG string. Only used for the
/// `fill` pass of a `polyline`-type path in paint mode with more than 2
/// points (`points.count > 2` per the spec's gate) — the stroke geometry
/// always comes from `samplePathPoints`/stamps/freehand, never this.
enum StrokeSmoothing {
    static func catmullRomPath(_ points: [Point], tension: Double = 0.5, closed: Bool = false) -> CGPath {
        let path = CGMutablePath()
        guard let first = points.first else { return path }
        path.move(to: CGPoint(x: first.x, y: first.y))
        guard points.count > 2 else {
            for p in points.dropFirst() { path.addLine(to: CGPoint(x: p.x, y: p.y)) }
            return path
        }
        for i in 0 ..< (points.count - 1) {
            let p0 = points[max(0, i - 1)]
            let p1 = points[i]
            let p2 = points[i + 1]
            let p3 = points[min(points.count - 1, i + 2)]
            let c1 = Point(x: p1.x + (p2.x - p0.x) * tension / 6, y: p1.y + (p2.y - p0.y) * tension / 6)
            let c2 = Point(x: p2.x - (p3.x - p1.x) * tension / 6, y: p2.y - (p3.y - p1.y) * tension / 6)
            path.addCurve(
                to: CGPoint(x: p2.x, y: p2.y),
                control1: CGPoint(x: c1.x, y: c1.y),
                control2: CGPoint(x: c2.x, y: c2.y)
            )
        }
        return path
    }
}
