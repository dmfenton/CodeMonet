import Foundation
import MonetProtocol

/// Bit-faithful Swift port of `perfect-freehand@1.2.3` (performer-render
/// spec §4), recovered from the vendored package's sourcemap
/// (`node_modules/perfect-freehand/dist/esm/index.mjs.map`). Used for: every
/// in-progress stroke tail/body (owned by the Studio-UI package, via this
/// public API), completed strokes in **plotter** mode (§8.3/§8.5), and every
/// bristle sub-stroke (§5, `Bristles.swift`). Not used for completed
/// paint-mode strokes — those go through the stamp model (`Stamping.swift`).
///
/// `MonetProtocol.Point` carries no `pressure` field (the wire protocol never
/// sends per-point pressure for agent-authored paths), so this port always
/// falls back to the library's default/first pressure — the same branch the
/// TS client takes for every agent stroke and every already-sampled
/// completed path.

/// One point in `getStrokePoints`'s resampled/smoothed output
/// (`StrokePoint`, spec §4.4).
public struct FreehandStrokePoint: Sendable {
    public var point: Point
    public var pressure: Double
    public var vector: Point
    public var distance: Double
    public var runningLength: Double
}

/// Cap/taper/easing options for one end of a stroke (`start`/`end` in the JS
/// options object, spec §4.5).
public struct FreehandCapOptions: Sendable {
    public enum Taper: Sendable, Equatable {
        /// `taper: false` (or unset) — no taper, a normal cap.
        case off
        /// `taper: true` — taper the full `max(size, totalLength)`.
        case full
        /// `taper: <number>` — taper over exactly this distance.
        case amount(Double)

        var isTapered: Bool { self != .off }
    }

    public var cap: Bool
    public var taper: Taper
    public var easing: @Sendable (Double) -> Double

    public init(cap: Bool = true, taper: Taper = .off, easing: @escaping @Sendable (Double) -> Double = { $0 }) {
        self.cap = cap
        self.taper = taper
        self.easing = easing
    }
}

/// `FreehandStrokeOptions` (spec §4.6). Every option perfect-freehand reads
/// in this app's usage — not the library's full surface (no custom `last`
/// per-point pressure input, since `Point` carries none).
public struct FreehandOptions: Sendable {
    public var size: Double
    public var thinning: Double
    public var smoothing: Double
    public var streamline: Double
    public var simulatePressure: Bool
    public var easing: @Sendable (Double) -> Double
    public var start: FreehandCapOptions
    public var end: FreehandCapOptions
    /// `options.last` — never set by any call site in this codebase (spec
    /// §4.4); kept for API completeness and defaults to `false`.
    public var last: Bool

    public init(
        size: Double = 16,
        thinning: Double = 0.5,
        smoothing: Double = 0.5,
        streamline: Double = 0.5,
        simulatePressure: Bool = true,
        easing: @escaping @Sendable (Double) -> Double = { $0 },
        start: FreehandCapOptions = FreehandCapOptions(),
        end: FreehandCapOptions = FreehandCapOptions(),
        last: Bool = false
    ) {
        self.size = size
        self.thinning = thinning
        self.smoothing = smoothing
        self.streamline = streamline
        self.simulatePressure = simulatePressure
        self.easing = easing
        self.start = start
        self.end = end
        self.last = last
    }
}

/// Standard easing functions the app's freehand options actually use (spec
/// §4.6), kept as named constants so call sites read like the TS source.
public enum FreehandEasing {
    /// The default start-taper easing, `t => t * (2 - t)`.
    public static let startDefault: @Sendable (Double) -> Double = { t in t * (2 - t) }
    /// The default end-taper easing, `t => --t * t * t + 1` (pre-decrement:
    /// evaluated at `t - 1`).
    public static let endDefault: @Sendable (Double) -> Double = { t in
        let u = t - 1
        return u * u * u + 1
    }
    /// `PAINTERLY_FREEHAND_OPTIONS`/`brushPresetToFreehandOptions`'s taper
    /// easing, `t => t * t`.
    public static let quadratic: @Sendable (Double) -> Double = { t in t * t }
}

public enum FreehandPresets {
    /// `DEFAULT_FREEHAND_OPTIONS` (spec §4.6) — untapered, size 8.
    public static let plotterDefault = FreehandOptions(
        size: 8, thinning: 0.5, smoothing: 0.5, streamline: 0.5, simulatePressure: true,
        start: FreehandCapOptions(cap: true, taper: .off),
        end: FreehandCapOptions(cap: true, taper: .off)
    )

    /// `PAINTERLY_FREEHAND_OPTIONS` (spec §4.6) — the paint-mode fallback
    /// when no brush preset is set. Note the §4.6 quirk this preserves: only
    /// `size` is overridden by the caller; `taper`/`thinning` stay fixed.
    public static func painterlyDefault(size: Double) -> FreehandOptions {
        FreehandOptions(
            size: size, thinning: 0.6, smoothing: 0.5, streamline: 0.4, simulatePressure: true,
            start: FreehandCapOptions(cap: true, taper: .amount(40), easing: FreehandEasing.quadratic),
            end: FreehandCapOptions(cap: true, taper: .amount(40), easing: FreehandEasing.quadratic)
        )
    }

    /// `brushPresetToFreehandOptions` (spec §4.6) — used whenever a brush is
    /// set, in either drawing mode's freehand renderer (plotter completed
    /// strokes never carry a brush per §8.3, but bristles/in-progress paint
    /// strokes do).
    public static func from(preset: BrushPreset, strokeWidth: Double) -> FreehandOptions {
        let taperAmount = preset.taper * strokeWidth
        return FreehandOptions(
            size: strokeWidth, thinning: preset.pressureResponse * 0.8, smoothing: preset.smoothing,
            streamline: 0.5, simulatePressure: true,
            start: FreehandCapOptions(cap: true, taper: .amount(taperAmount), easing: FreehandEasing.quadratic),
            end: FreehandCapOptions(cap: true, taper: .amount(taperAmount), easing: FreehandEasing.quadratic)
        )
    }
}

/// `applyVelocityPressure` (spec §4.7) — rescales `options.size` for the
/// in-progress tail based on recent point spacing. Slower movement (small
/// average distance) thickens the tail; fast movement thins it.
///
/// `fallbackSize` mirrors the JS signature's `options.size ?? fallbackSize`;
/// every call site in this port always populates `options.size` explicitly
/// (`FreehandOptions.size` isn't optional), so it's a no-op here — kept for
/// API/documentation parity with the source.
public func applyVelocityPressure(points: [Point], options: FreehandOptions, fallbackSize: Double) -> FreehandOptions {
    guard points.count >= 2 else { return options }
    var total = 0.0
    for i in 1 ..< points.count {
        total += Vec2.distance(points[i], points[i - 1])
    }
    let avgDist = total / Double(points.count - 1)
    let pressureFactor = min(1.2, max(0.6, 1.0 / (1 + avgDist * 0.015)))
    var adjusted = options
    adjusted.size = options.size * pressureFactor
    return adjusted
}

/// Not `private`: shared with `FreehandOutline.swift`'s outline walk (the
/// caps/corner-fan/taper math), which this file's types feed into.
enum FreehandConstants {
    static let rateOfPressureChange = 0.275
    /// `FIXED_PI` — plain `PI` in Swift; the `+0.0001` fudge exists only to
    /// dodge a browser rendering artifact (spec §4.1).
    static let fixedPi = Double.pi
    static let startCapSegments = 13
    static let endCapSegments = 29
    static let cornerCapSegments = 13
    static let endNoiseThreshold = 3.0
    static let minStreamlineT = 0.15
    static let streamlineTRange = 0.85
    static let minRadius = 0.01
    static let defaultFirstPressure = 0.25
    static let defaultPressure = 0.5
    static let unitOffset = Point(x: 1, y: 1)
}

/// Not `private`: also called from `FreehandOutline.swift`'s per-point
/// radius resolution.
func strokeRadius(size: Double, thinning: Double, pressure: Double, easing: (Double) -> Double) -> Double {
    size * easing(0.5 - thinning * (0.5 - pressure))
}

/// Not `private`: also called from `FreehandOutline.swift`.
func simulatedPressure(prevPressure: Double, distance: Double, size: Double) -> Double {
    let speedOfChange = min(1, distance / size)
    let rateOfChange = min(1, 1 - speedOfChange)
    return min(1, prevPressure + (rateOfChange - prevPressure) * (speedOfChange * FreehandConstants.rateOfPressureChange))
}

/// `getStrokePoints` (spec §4.4): resample + smooth the input polyline,
/// tracking a running arc length. `Point` carries no pressure, so every
/// point uses the library's default pressure fallback.
func getStrokePoints(_ inputPoints: [Point], options: FreehandOptions) -> [FreehandStrokePoint] {
    if inputPoints.isEmpty { return [] }

    let t = FreehandConstants.minStreamlineT + (1 - options.streamline) * FreehandConstants.streamlineTRange

    var pts = inputPoints
    if pts.count == 2 {
        let first = pts[0]
        let last = pts[1]
        pts = [first]
        for i in 1 ..< 5 {
            pts.append(Vec2.lerp(first, last, Double(i) / 4.0))
        }
    }
    if pts.count == 1 {
        pts = [pts[0], Vec2.add(pts[0], FreehandConstants.unitOffset)]
    }

    var strokePoints = [
        FreehandStrokePoint(
            point: pts[0], pressure: FreehandConstants.defaultFirstPressure,
            vector: FreehandConstants.unitOffset, distance: 0, runningLength: 0
        ),
    ]

    var hasReachedMinimumLength = false
    var runningLength = 0.0
    var prev = strokePoints[0]
    let maxIndex = pts.count - 1

    for i in 1 ..< pts.count {
        let point: Point = (options.last && i == maxIndex) ? pts[i] : Vec2.lerp(prev.point, pts[i], t)
        if point == prev.point { continue }

        let distance = Vec2.distance(point, prev.point)
        runningLength += distance

        if i < maxIndex, !hasReachedMinimumLength {
            if runningLength < options.size { continue }
            hasReachedMinimumLength = true
        }

        let vector = Vec2.normalized(Vec2.sub(prev.point, point))
        prev = FreehandStrokePoint(
            point: point, pressure: FreehandConstants.defaultPressure,
            vector: vector, distance: distance, runningLength: runningLength
        )
        strokePoints.append(prev)
    }

    strokePoints[0].vector = strokePoints.count > 1 ? strokePoints[1].vector : Point(x: 0, y: 0)
    return strokePoints
}
