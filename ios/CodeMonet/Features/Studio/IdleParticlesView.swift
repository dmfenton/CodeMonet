import SwiftUI

/// Floating particles shown while the canvas is truly empty
/// (`StudioSelectors.shouldShowIdleAnimation`, ux spec §2/§6.2). A
/// SwiftUI/`TimelineView`-driven equivalent of the RN app's
/// Skia+Reanimated `SkiaIdleParticles` — same particle count and soft
/// artistic palette, drifting gently on a 15s loop.
struct IdleParticlesView: View {
    let canvasSize: CGSize

    private static let particleCount = 12
    fileprivate static let cycleDuration: Double = 15
    private static let colors: [Color] = [
        Color(hex: "#7b68ee").opacity(0.3), // Lavender
        Color(hex: "#4ecdc4").opacity(0.3), // Teal
        Color(hex: "#ff6b6b").opacity(0.25), // Coral
        Color(hex: "#ffd93d").opacity(0.2), // Gold
        Color(hex: "#e94560").opacity(0.25), // Rose
    ]

    private let particles: [Particle] = Self.generate()

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { context in
            Canvas { canvasContext, size in
                guard canvasSize.width > 0, canvasSize.height > 0 else { return }
                let scaleX = size.width / canvasSize.width
                let scaleY = size.height / canvasSize.height
                let elapsed = context.date.timeIntervalSinceReferenceDate

                for particle in particles {
                    let (position, opacity) = particle.state(at: elapsed)
                    let point = CGPoint(x: position.x * scaleX, y: position.y * scaleY)
                    let rect = CGRect(x: point.x - particle.radius, y: point.y - particle.radius, width: particle.radius * 2, height: particle.radius * 2)
                    canvasContext.opacity = opacity
                    canvasContext.fill(Path(ellipseIn: rect), with: .color(particle.color))
                }
            }
        }
        .accessibilityHidden(true)
    }

    private static func generate() -> [Particle] {
        var generator = SeededGenerator(seed: 0x1DEA_9042)
        return (0 ..< particleCount).map { index in
            let startX = Double.random(in: 0 ..< 800, using: &generator)
            let startY = Double.random(in: 0 ..< 600, using: &generator)
            let angle = Double.random(in: 0 ..< (2 * .pi), using: &generator)
            let distance = 100 + Double.random(in: 0 ..< 200, using: &generator)
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
