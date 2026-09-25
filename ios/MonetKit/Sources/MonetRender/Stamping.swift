import Foundation
import MonetProtocol

/// Swift port of `shared/src/renderer/stamping.ts` (performer-render spec
/// §7) — the only renderer used for **completed** strokes in paint mode.
/// Deterministic given `(points, style, brush)`: same `Mulberry32` seed
/// sequence every time, matching the spec's load-bearing determinism
/// requirement (a gallery piece must render identically on every reload, and
/// `render-study.py --compare`'s pixel-diff parity depends on it).

/// 8-bit RGB color (spec §7.4.3).
public struct Rgb: Equatable, Sendable {
    public var r: Int
    public var g: Int
    public var b: Int

    public init(r: Int, g: Int, b: Int) {
        self.r = r
        self.g = g
        self.b = b
    }
}

/// `hexToRgb` (`stamping.ts:282-296`): tolerates `#rgb` shorthand; an
/// invalid/short channel silently becomes 0 (mirrors `parseInt(...) || 0`),
/// never a crash.
func hexToRgb(_ hex: String) -> Rgb {
    var value = hex
    if value.hasPrefix("#") { value.removeFirst() }
    if value.count == 3 {
        value = value.map { "\($0)\($0)" }.joined()
    }
    let chars = Array(value)
    func channel(_ start: Int, _ end: Int) -> Int {
        guard start < chars.count else { return 0 }
        let clampedEnd = min(end, chars.count)
        guard clampedEnd > start else { return 0 }
        return Int(String(chars[start ..< clampedEnd]), radix: 16) ?? 0
    }
    return Rgb(r: channel(0, 2), g: channel(2, 4), b: channel(4, 6))
}

func clamp01(_ v: Double) -> Double { v < 0 ? 0 : (v > 1 ? 1 : v) }

private struct Hsv {
    var h: Double
    var s: Double
    var v: Double
}

private func rgbToHsv(_ rgb: Rgb) -> Hsv {
    let r = Double(rgb.r) / 255
    let g = Double(rgb.g) / 255
    let b = Double(rgb.b) / 255
    let maxValue = max(r, g, b)
    let minValue = min(r, g, b)
    let delta = maxValue - minValue
    var h = 0.0
    if delta > 0 {
        if maxValue == r {
            h = ((g - b) / delta).truncatingRemainder(dividingBy: 6)
        } else if maxValue == g {
            h = (b - r) / delta + 2
        } else {
            h = (r - g) / delta + 4
        }
        h /= 6
        if h < 0 { h += 1 }
    }
    let s = maxValue == 0 ? 0 : delta / maxValue
    return Hsv(h: h, s: s, v: maxValue)
}

private func hsvToRgb(_ h: Double, _ s: Double, _ v: Double) -> Rgb {
    let i = Int(floor(h * 6))
    let f = h * 6 - Double(i)
    let p = v * (1 - s)
    let q = v * (1 - f * s)
    let t = v * (1 - (1 - f) * s)
    var r = 0.0, g = 0.0, b = 0.0
    switch ((i % 6) + 6) % 6 {
    case 0: r = v; g = t; b = p
    case 1: r = q; g = v; b = p
    case 2: r = p; g = v; b = t
    case 3: r = p; g = q; b = v
    case 4: r = t; g = p; b = v
    default: r = v; g = p; b = q
    }
    return Rgb(r: Int((r * 255).rounded()), g: Int((g * 255).rounded()), b: Int((b * 255).rounded()))
}

/// `jitterColor` (spec §7.4.3): per-stamp broken color, consuming exactly 3
/// `rng()` draws (hue, sat, val) in that order.
func jitterColor(_ rgb: Rgb, rng: inout Mulberry32, dyn: StampDynamics) -> Rgb {
    let hsv = rgbToHsv(rgb)
    let h2 = (hsv.h + (rng.next() * 2 - 1) * dyn.hueJitter + 1).truncatingRemainder(dividingBy: 1)
    let s2 = clamp01(hsv.s + (rng.next() * 2 - 1) * dyn.satJitter * (0.3 + hsv.s))
    let v2 = clamp01(hsv.v + (rng.next() * 2 - 1) * dyn.valJitter)
    return hsvToRgb(h2, s2, v2)
}

/// `smoothNoise` (spec §7.4.1): low-frequency multiplicative noise around
/// 1.0, smoothstepped between `knots` random control values. Consumes
/// exactly `knots` `rng()` draws, in order, before returning.
func smoothNoise(rng: inout Mulberry32, n: Int, scale: Double) -> [Double] {
    guard n > 0 else { return [] }
    let knots = max(2, n / 6)
    var vals: [Double] = []
    vals.reserveCapacity(knots)
    for _ in 0 ..< knots { vals.append(rng.next() * 2 - 1) }

    var out: [Double] = []
    out.reserveCapacity(n)
    for i in 0 ..< n {
        let t = (Double(i) / Double(max(1, n - 1))) * Double(knots - 1)
        let k = min(Int(t), knots - 2)
        var f = t - Double(k)
        f = f * f * (3 - 2 * f)
        out.append(1 + (vals[k] * (1 - f) + vals[k + 1] * f) * scale)
    }
    return out
}

/// `taperProfile` (spec §7.4.2): eases the head over `t ∈ [0, 0.18]` and the
/// tail over `t ∈ [0.7, 1]`, full width in between.
func taperProfile(_ t: Double, _ taper: Double) -> Double {
    var ease = 1.0
    if t < 0.18 {
        let head = min(1, t / 0.18)
        ease = head * (0.4 + 0.6 * head)
    } else if t > 0.7 {
        let tail = min(1, (1 - t) / 0.3)
        ease = tail * (0.4 + 0.6 * tail)
    }
    return 1 - taper * (1 - ease)
}

private struct ResampledPoint {
    var x: Double
    var y: Double
    var angle: Double
}

private let maxStampsPerStroke = 700

/// `resample` (spec §7.3): arc-length-uniform resample of `points` to stamp
/// centers, each carrying the local segment's tangent angle.
private func resample(_ points: [Point], spacing: Double) -> [ResampledPoint] {
    guard points.count >= 2 else {
        guard let p = points.first else { return [] }
        return [ResampledPoint(x: p.x, y: p.y, angle: 0)]
    }

    var segLen: [Double] = []
    segLen.reserveCapacity(points.count - 1)
    var total = 0.0
    for i in 1 ..< points.count {
        let len = Vec2.distance(points[i], points[i - 1])
        segLen.append(len)
        total += len
    }

    let effSpacing = max(spacing, total / Double(maxStampsPerStroke), 0.75)
    let n = max(2, Int(floor(total / effSpacing)) + 1)

    var out: [ResampledPoint] = []
    out.reserveCapacity(n)
    var j = 0
    var cum = 0.0
    for k in 0 ..< n {
        let target = (Double(k) / Double(n - 1)) * total
        while j < segLen.count - 1, cum + segLen[j] < target {
            cum += segLen[j]
            j += 1
        }
        let denom = max(1e-6, segLen[j])
        let f = (target - cum) / denom
        let p0 = points[j]
        let p1 = points[j + 1]
        out.append(ResampledPoint(
            x: p0.x + (p1.x - p0.x) * f,
            y: p0.y + (p1.y - p0.y) * f,
            angle: atan2(p1.y - p0.y, p1.x - p0.x)
        ))
    }
    return out
}

/// One oriented, tinted "dab" (spec §7, `Stamp` interface).
public struct Stamp: Sendable {
    public var x: Double
    public var y: Double
    /// Tangent angle in radians, canvas (screen, y-down) coordinates.
    public var angle: Double
    public var length: Double
    public var width: Double
    /// Already includes load fade and the stroke's own opacity.
    public var alpha: Double
    public var variant: Int
    public var color: Rgb
}

/// The subset of `StrokeStyle` the stamp model needs (spec §7.4's
/// `computeStrokeStamps` signature).
public struct StampStrokeStyle: Sendable {
    public var color: String
    public var strokeWidth: Double
    public var opacity: Double

    public init(color: String, strokeWidth: Double, opacity: Double) {
        self.color = color
        self.strokeWidth = strokeWidth
        self.opacity = opacity
    }
}

public let spriteVariantCount = 4

/// `computeStrokeStamps` (spec §7.4): decompose an already-sampled stroke
/// into stamps. RNG consumption order is load-bearing for reproducing the
/// reference render exactly — see the spec's §7.4 note: `smoothNoise` draws
/// all its knots up front, then each stamp draws `load` -> (`dryness`?) ->
/// `jitterColor`'s 3 draws, in that order, even for stamps later discarded
/// by the `alpha <= 0.004` gate (which runs after those draws).
public func computeStrokeStamps(points: [Point], style: StampStrokeStyle, brush: BrushName?) -> [Stamp] {
    guard points.count >= 2, style.opacity > 0 else { return [] }
    let dyn = StampDynamics.dynamics(for: brush)
    let width = max(1.5, style.strokeWidth)
    var rng = Mulberry32(seed: Mulberry32.strokeSeed(points: points, width: width))
    let base = hexToRgb(style.color)

    let stampsRaw = resample(points, spacing: max(1.0, width * dyn.spacing))
    let n = stampsRaw.count
    guard n > 0 else { return [] }
    let wobble = smoothNoise(rng: &rng, n: n, scale: dyn.widthWobble)

    // Short marks (dabs) don't taper/deplete like long strokes.
    let lengthFactor = min(1, Double(n) / 10)
    let taper = dyn.taper * lengthFactor
    let loadFade = dyn.loadFade * lengthFactor

    // Per-stamp alpha calibrated so accumulated overlap approximates the
    // requested stroke opacity.
    let overlap = max(1, (dyn.aspect / dyn.spacing) * 0.45)
    let target = min(0.985, style.opacity)
    let stampAlpha = 1 - pow(1 - target, 1 / overlap)

    var out: [Stamp] = []
    out.reserveCapacity(n)
    for i in 0 ..< n {
        let t = Double(i) / Double(max(1, n - 1))
        let w = width * taperProfile(t, taper) * wobble[i]
        if w < 0.6 { continue }

        let load = 1 - loadFade * pow(t, 1.3) * (0.7 + rng.next() * 0.3)
        var alpha = stampAlpha * load
        if dyn.wetEdge > 0, t < 0.08 || t > 0.92 {
            alpha = min(1, alpha * (1 + dyn.wetEdge))
        }
        if dyn.dryness > 0 {
            // No shared canvas-tooth map on this port (server-only, §13):
            // approximate dry breakup with per-stamp alpha noise that gets
            // stronger as the load drops.
            let dry = dyn.dryness * (0.5 + 0.5 * (1 - load))
            alpha *= max(0, 1 - dry * rng.next() * 1.6)
        }
        let color = jitterColor(base, rng: &rng, dyn: dyn)
        if alpha <= 0.004 { continue }

        let stamp = stampsRaw[i]
        out.append(Stamp(
            x: stamp.x, y: stamp.y, angle: stamp.angle,
            length: w * dyn.aspect * 1.1 + 1,
            width: w * 1.1 + 1,
            alpha: alpha,
            variant: (i * 7) % spriteVariantCount,
            color: color
        ))
    }
    return out
}

// ---------------------------------------------------------------------------
// Sprite alpha texture (spec §7.5)
// ---------------------------------------------------------------------------

/// One alpha-only "dab" texture for `(brush, variant)`. Row-major, `width`
/// is the along-stroke pixel count (the sprite's *columns*), `height` is the
/// across-stroke pixel count — field names intentionally match the TS
/// source's swap (`stamping.ts:741`), since the sprite is authored
/// horizontally (along-stroke) but the draw call anchors it by its
/// across-stroke axis.
public struct SpriteAlpha: Sendable {
    public var width: Int
    public var height: Int
    public var data: [Float]
}

public let spriteBaseWidth = 48

/// Bilinear upsample of a coarse `rng()`-filled grid to `(w, h)`. Consumes
/// exactly `coarseW * coarseH` draws, before any of the caller's later
/// draws.
private func upsampleNoise(rng: inout Mulberry32, coarseW: Int, coarseH: Int, w: Int, h: Int) -> [Float] {
    var coarse = [Float](repeating: 0, count: coarseW * coarseH)
    for i in 0 ..< coarse.count { coarse[i] = Float(rng.next()) }

    var out = [Float](repeating: 0, count: w * h)
    for y in 0 ..< h {
        let gy = (Double(y) / Double(max(1, h - 1))) * Double(coarseH - 1)
        let y0 = min(Int(gy), coarseH - 2)
        let fy = gy - Double(y0)
        for x in 0 ..< w {
            let gx = (Double(x) / Double(max(1, w - 1))) * Double(coarseW - 1)
            let x0 = min(Int(gx), coarseW - 2)
            let fx = gx - Double(x0)
            let a = Double(coarse[y0 * coarseW + x0])
            let b = Double(coarse[y0 * coarseW + x0 + 1])
            let c = Double(coarse[(y0 + 1) * coarseW + x0])
            let d = Double(coarse[(y0 + 1) * coarseW + x0 + 1])
            out[y * w + x] = Float(a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy)
        }
    }
    return out
}

/// `generateSpriteAlpha` (spec §7.5). RNG consumption order matters:
/// `edgeNoise` grid (if `edgeRough > 0`) -> streak `rows` (if applicable) ->
/// the per-texel double loop (`y` outer, `x` inner) — reproduce this order
/// exactly or the sprite texture desyncs from the reference.
public func generateSpriteAlpha(brush: BrushName?, variant: Int) -> SpriteAlpha {
    let dyn = StampDynamics.dynamics(for: brush)
    let width = spriteBaseWidth
    let length = max(8, Int((Double(width) * dyn.aspect).rounded()))
    var rng = Mulberry32(seed: Mulberry32.spriteSeed(brushName: brush?.rawValue ?? "default", variant: variant))

    let plateau = 2.2 - dyn.soften * 1.4
    let exponent = 0.6 + dyn.soften * 0.9

    let edgeNoise: [Float]? = dyn.edgeRough > 0 ? upsampleNoise(rng: &rng, coarseW: 8, coarseH: 6, w: length, h: width) : nil

    var rowGain = [Double](repeating: 1, count: width)
    if dyn.streaks > 0, dyn.streakContrast > 0 {
        var rows = [Double](repeating: 0, count: dyn.streaks)
        for i in 0 ..< dyn.streaks { rows[i] = rng.next() }
        for y in 0 ..< width {
            let t = (Double(y) / Double(max(1, width - 1))) * Double(dyn.streaks - 1)
            let k = min(Int(t), max(0, dyn.streaks - 2))
            let f = t - Double(k)
            let nextK = min(k + 1, dyn.streaks - 1)
            let v = rows[k] * (1 - f) + rows[nextK] * f
            rowGain[y] = 1 - dyn.streakContrast + dyn.streakContrast * (0.35 + 0.9 * v)
        }
    }

    var data = [Float](repeating: 0, count: width * length)
    for y in 0 ..< width {
        let ny = (Double(y) / Double(width - 1)) * 2 - 1
        for x in 0 ..< length {
            let nx = (Double(x) / Double(length - 1)) * 2 - 1
            let r2 = nx * nx + ny * ny
            var body = pow(clamp01(plateau * (1 - r2)), exponent)

            if let edgeNoise, dyn.edgeRough > 0 {
                let rim = clamp01((r2 - (1 - dyn.edgeRough * 0.9)) / (dyn.edgeRough * 0.9 + 1e-6))
                body *= 1 - rim * (0.3 + 0.7 * Double(edgeNoise[y * length + x]))
            }

            let run = 0.6 + 0.4 * clamp01(1.2 - abs(nx))
            body *= min(1.3, rowGain[y] * run)

            body *= 0.92 + 0.08 * rng.next()

            data[y * length + x] = Float(clamp01(body))
        }
    }

    return SpriteAlpha(width: length, height: width, data: data)
}
