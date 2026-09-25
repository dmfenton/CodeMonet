import Foundation
import MonetProtocol

/// Bit-exact port of the client's `mulberry32` PRNG (performer-render spec
/// §7.1). All arithmetic is unsigned 32-bit with wraparound — this must stay
/// bit-identical to the TypeScript implementation, since stamp placement
/// determinism (same seed -> same pixels, forever, on every platform) is
/// load-bearing for gallery-piece reproducibility and for
/// `render-study.py --compare`'s pixel-diff parity harness.
public struct Mulberry32: Sendable {
    private var state: UInt32

    public init(seed: UInt32) {
        state = seed
    }

    /// Returns the next value in `[0, 1)`, matching the JS reference's
    /// `>>> 0) / 4294967296` normalization exactly.
    public mutating func next() -> Double {
        state = state &+ 0x6D2B_79F5
        var t = state
        t = imul(t ^ (t >> 15), t | 1)
        t ^= t &+ imul(t ^ (t >> 7), t | 61)
        return Double((t ^ (t >> 14))) / 4_294_967_296.0
    }

    /// `Math.imul(a, b)`: the low 32 bits of the signed 32-bit product.
    private func imul(_ a: UInt32, _ b: UInt32) -> UInt32 {
        UInt32(truncatingIfNeeded: Int64(Int32(bitPattern: a)) * Int64(Int32(bitPattern: b)))
    }

    /// `strokeSeed` (performer-render spec §7.1): derives a per-stroke seed
    /// from its (already-sampled, §3) point list and effective width.
    public static func strokeSeed(points: [Point], width: Double) -> UInt32 {
        let sum = points.reduce(0.0) { $0 + $1.x * 17.0 + $1.y * 31.0 }
        let widthComponent = UInt32(truncatingIfNeeded: Int64((width * 7).rounded(.down)))
        let sumComponent = UInt32(truncatingIfNeeded: Int64(sum.rounded(.down)))
        return sumComponent ^ widthComponent
    }

    /// Sprite seed for `(brush, variant)` (performer-render spec §7.1).
    /// `brushName` defaults to the literal `"default"` when no brush is set
    /// — matching that exactly matters for reproducing the no-brush sprite.
    public static func spriteSeed(brushName: String, variant: Int) -> UInt32 {
        var seed = UInt32(truncatingIfNeeded: variant * 7919 + 17)
        for scalar in brushName.unicodeScalars {
            seed = seed &* 31 &+ scalar.value
        }
        return seed
    }
}
