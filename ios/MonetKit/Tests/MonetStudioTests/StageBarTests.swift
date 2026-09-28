import Foundation
@testable import MonetStudio
import Testing

@Suite("Stage bar")
struct StageBarTests {
    private func stage(_ label: String, weight: Double) -> StageSpec {
        StageSpec(label: label, weight: weight)
    }

    @Test("widths are proportional to stage weights when every stage clears the floor")
    func proportional() {
        let segments = StageBar.segments(
            stages: [stage("ground", weight: 100), stage("sky", weight: 200), stage("water", weight: 100)],
            active: nil
        )
        #expect(segments.map(\.label) == ["ground", "sky", "water"])
        #expect(segments.map(\.fraction) == [0.25, 0.5, 0.25])
        #expect(segments.allSatisfy { $0.progress == .done })
    }

    @Test("tiny stages get the floor and the rest shrink proportionally")
    func floorKeepsSmallStagesVisible() {
        let segments = StageBar.segments(
            stages: [stage("ground", weight: 1), stage("sky", weight: 300), stage("glaze", weight: 100)],
            active: nil,
            minimumFraction: 0.1
        )
        let fractions = segments.map(\.fraction)
        #expect(abs(fractions.reduce(0, +) - 1) < 1e-9)
        #expect(abs(fractions[0] - 0.1) < 1e-9)
        #expect(abs(fractions[1] - 0.9 * 0.75) < 1e-9)
        #expect(abs(fractions[2] - 0.9 * 0.25) < 1e-9)
    }

    @Test("all-zero weights split the bar evenly")
    func zeroOpsEvenSplit() {
        let fractions = StageBar.flooredFractions([0, 0, 0, 0], minimum: 0.1)
        #expect(fractions == [0.25, 0.25, 0.25, 0.25])
    }

    @Test("the active stage is current; earlier are done, later pending")
    func currentStage() {
        let segments = StageBar.segments(
            stages: [stage("ground", weight: 10), stage("sky", weight: 10), stage("poplars", weight: 10), stage("water", weight: 10)],
            active: 2
        )
        #expect(segments.map(\.progress) == [.done, .done, .current, .pending])
        // Past the last stage = fully shown.
        let finished = StageBar.segments(stages: [stage("ground", weight: 10)], active: 5)
        #expect(finished.map(\.progress) == [.done])
    }

    @Test("consecutive stages with one label merge into one segment")
    func mergesConsecutiveLabels() {
        let segments = StageBar.segments(
            stages: [stage("sky", weight: 10), stage("sky", weight: 30), stage("sea", weight: 40)],
            active: 1
        )
        #expect(segments.map(\.label) == ["sky", "sea"])
        #expect(segments.map(\.weight) == [40, 40])
        #expect(segments.map(\.id) == [0, 2])
        #expect(segments.map(\.progress) == [.current, .pending])
    }
}
