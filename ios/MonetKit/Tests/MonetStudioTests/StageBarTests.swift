import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

@Suite("Stage bar")
struct StageBarTests {
    private func keyframe(_ label: String, ops count: Int) -> RevealKeyframe {
        RevealKeyframe(
            label: label,
            image: "kf.jpg",
            ops: Array(repeating: .stroke(width: 2, points: [Point(x: 0, y: 0)]), count: count)
        )
    }

    private func manifest(_ keyframes: [RevealKeyframe]) -> RevealManifest {
        RevealManifest(width: 100, height: 100, keyframes: keyframes)
    }

    @Test("widths are proportional to op counts when every stage clears the floor")
    func proportional() {
        let segments = StageBar.segments(
            manifest: manifest([keyframe("ground", ops: 100), keyframe("sky", ops: 200), keyframe("water", ops: 100)]),
            revealingKeyframe: nil
        )
        #expect(segments.map(\.label) == ["ground", "sky", "water"])
        #expect(segments.map(\.fraction) == [0.25, 0.5, 0.25])
        #expect(segments.allSatisfy { $0.progress == .done })
    }

    @Test("tiny stages get the floor and the rest shrink proportionally")
    func floorKeepsSmallStagesVisible() {
        let segments = StageBar.segments(
            manifest: manifest([keyframe("ground", ops: 1), keyframe("sky", ops: 300), keyframe("glaze", ops: 100)]),
            revealingKeyframe: nil,
            minimumFraction: 0.1
        )
        let fractions = segments.map(\.fraction)
        #expect(abs(fractions.reduce(0, +) - 1) < 1e-9)
        #expect(abs(fractions[0] - 0.1) < 1e-9)
        #expect(abs(fractions[1] - 0.9 * 0.75) < 1e-9)
        #expect(abs(fractions[2] - 0.9 * 0.25) < 1e-9)
    }

    @Test("all-zero op counts split the bar evenly")
    func zeroOpsEvenSplit() {
        let fractions = StageBar.flooredFractions([0, 0, 0, 0], minimum: 0.1)
        #expect(fractions == [0.25, 0.25, 0.25, 0.25])
    }

    @Test("the revealing keyframe is current; earlier are done, later pending")
    func currentStage() {
        let segments = StageBar.segments(
            manifest: manifest([keyframe("ground", ops: 10), keyframe("sky", ops: 10), keyframe("poplars", ops: 10), keyframe("water", ops: 10)]),
            revealingKeyframe: 2
        )
        #expect(segments.map(\.progress) == [.done, .done, .current, .pending])
        // Past the last keyframe = fully revealed.
        let finished = StageBar.segments(manifest: manifest([keyframe("ground", ops: 10)]), revealingKeyframe: 5)
        #expect(finished.map(\.progress) == [.done])
    }

    @Test("consecutive keyframes with one label merge into one segment")
    func mergesConsecutiveLabels() {
        let segments = StageBar.segments(
            manifest: manifest([keyframe("sky", ops: 10), keyframe("sky", ops: 30), keyframe("sea", ops: 40)]),
            revealingKeyframe: 1
        )
        #expect(segments.map(\.label) == ["sky", "sea"])
        #expect(segments.map(\.opCount) == [40, 40])
        #expect(segments.map(\.id) == [0, 2])
        #expect(segments.map(\.progress) == [.current, .pending])
    }
}
