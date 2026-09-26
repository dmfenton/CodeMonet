import SwiftUI

/// Floating particles shown while the canvas is truly empty
/// (`StudioSelectors.shouldShowIdleAnimation`, ux spec §2/§6.2). A
/// SwiftUI/`TimelineView`-driven equivalent of the RN app's
/// Skia+Reanimated `SkiaIdleParticles` — same particle count and soft
/// artistic palette, drifting gently on a 15s loop.
struct IdleParticlesView: View {
    private static let particleCount = 12
    fileprivate static let cycleDuration: Double = 15
    /// Brand tones from the light palette — the canvas paper stays light in
    /// both color schemes, so these never adapt.
    private static let colors: [Color] = {
        let light = CodeMonetDesignSystem.theme.light
        return [
            light.accent.opacity(0.22),
            light.emphasis.opacity(0.22),
            light.success.opacity(0.22),
            light.warning.opacity(0.18),
            CodeMonetDesignSystem.Extra.humanStroke.opacity(0.18),
        ]
    }()

    private let particles: [Particle] = Self.generate()

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { context in
            Canvas { canvasContext, size in
                guard size.width > 0, size.height > 0 else { return }
                let elapsed = context.date.timeIntervalSinceReferenceDate

                for particle in particles {
                    let (position, opacity) = particle.state(at: elapsed)
                    let point = CGPoint(x: position.x * size.width, y: position.y * size.height)
                    let rect = CGRect(x: point.x - particle.radius, y: point.y - particle.radius, width: particle.radius * 2, height: particle.radius * 2)
                    canvasContext.opacity = opacity
                    canvasContext.fill(Path(ellipseIn: rect), with: .color(particle.color))
                }
            }
        }
        .accessibilityHidden(true)
    }

    /// Positions/radii are generated in normalized `0..<1` space (fractions
    /// of whatever container this view is given) rather than a hardcoded
    /// pixel box, so the particle field fills the actual current canvas
    /// evenly regardless of its size profile (800x600, 1200x420, 800x800,
    /// 600x900, 1200x600 — see `CanvasSizeProfile`).
    private static func generate() -> [Particle] {
        var generator = SeededGenerator(seed: 0x1DEA_9042)
        return (0 ..< particleCount).map { index in
            let startX = Double.random(in: 0 ..< 1, using: &generator)
            let startY = Double.random(in: 0 ..< 1, using: &generator)
            let angle = Double.random(in: 0 ..< (2 * .pi), using: &generator)
            // Drift distance as a fraction of the container, roughly
            // matching the old 100-300px drift against an 800x600 box.
            let distance = 0.15 + Double.random(in: 0 ..< 0.25, using: &generator)
            return Particle(
                start: CGPoint(x: startX, y: startY),
                end: CGPoint(x: startX + cos(angle) * distance, y: startY + sin(angle) * distance),
                radius: 4 + Double.random(in: 0 ..< 12, using: &generator),
                color: colors[index % colors.count],
                phaseOffset: Double.random(in: 0 ..< cycleDuration, using: &generator)
            )
        }
    }
}

private struct Particle {
    let start: CGPoint
    let end: CGPoint
    let radius: Double
    let color: Color
    let phaseOffset: Double

    /// Ping-pongs between `start` and `end` on a fade-in/drift/fade-out
    /// cycle, looping every `IdleParticlesView.cycleDuration` seconds.
    func state(at elapsed: TimeInterval) -> (position: CGPoint, opacity: Double) {
        let duration = IdleParticlesView.cycleDuration
        let t = (elapsed + phaseOffset).truncatingRemainder(dividingBy: duration) / duration
        let eased = t < 0.5 ? 2 * t * t : 1 - pow(-2 * t + 2, 2) / 2
        let x = start.x + (end.x - start.x) * eased
        let y = start.y + (end.y - start.y) * eased
        let opacity = sin(t * .pi) // fades in, peaks mid-cycle, fades out
        return (CGPoint(x: x, y: y), opacity)
    }
}

/// A tiny deterministic PRNG so idle particles are stable across a single
/// app launch's redraws (regenerated once per `IdleParticlesView` instance)
/// without depending on `SystemRandomNumberGenerator` — keeps this view's
/// layout reproducible for previews/tests.
private struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed == 0 ? 0x9E37_79B9_7F4A_7C15 : seed
    }

    mutating func next() -> UInt64 {
        state ^= state << 13
        state ^= state >> 7
        state ^= state << 17
        return state
    }
}
