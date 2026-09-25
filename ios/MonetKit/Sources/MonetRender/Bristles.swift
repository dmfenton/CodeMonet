import MonetProtocol

/// `getBristleOutlines` (performer-render spec §5): one independent
/// perfect-freehand outline per bristle, offset from the shared centerline
/// by jitter. Only produced for brush presets with `bristleCount > 0`.
///
/// This uses a non-seeded RNG on purpose — the spec is explicit that bristle
/// jitter (unlike the stamp model, §7) has no reproducibility requirement,
/// since it's drawn fresh from `Math.random()` on the TS side too.
public func getBristleOutlines(
    inputPoints: [Point],
    bristleCount: Int,
    spread: Double,
    options: FreehandOptions
) -> [[Point]] {
    guard !inputPoints.isEmpty, bristleCount > 0 else { return [] }

    let bristleSize = options.size * 0.3
    var bristles: [[Point]] = []
    bristles.reserveCapacity(bristleCount)

    for i in 0 ..< bristleCount {
        let denominator = bristleCount > 1 ? Double(bristleCount - 1) : 1
        let offset = bristleCount > 1 ? ((Double(i) / denominator) - 0.5) * spread * 2 : 0

        let jittered = inputPoints.map { p in
            Point(
                x: p.x + offset + (Double.random(in: 0 ..< 1) - 0.5) * spread * 0.3,
                y: p.y + (Double.random(in: 0 ..< 1) - 0.5) * spread * 0.3
            )
        }

        var bristleOptions = options
        bristleOptions.size = bristleSize
        bristleOptions.thinning = 0.3
        bristles.append(getFreehandOutline(jittered, options: bristleOptions))
    }

    return bristles
}
