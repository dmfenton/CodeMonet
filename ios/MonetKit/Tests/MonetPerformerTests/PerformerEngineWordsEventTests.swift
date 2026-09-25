import Foundation
@testable import MonetPerformer
@testable import MonetProtocol
@testable import MonetStudio
import Testing

/// Covers the `'words'`/`'event'` performance items (spec §11.2-11.3), the
/// leading-batch style override (§11.4), and the idle-particle gate (§11.7)
/// — split from `PerformerEngineTests` to keep each file under the repo's
/// file-length lint budget.
@Suite("PerformerEngine words/event/idle")
struct PerformerEngineWordsEventTests {
    // MARK: - §11.4 style override on the leading batch only

    @Test("leading batch carries a style override only for the fields the path actually set")
    func leadingBatchStyleOnlySetFields() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let stroke = PendingStroke(
            batchId: 1,
            path: Path(type: .line, points: [Point(x: 0, y: 0)], color: "#abcdef"),
            points: [Point(x: 0, y: 0), Point(x: 5, y: 0)]
        )
        var state = StudioState()
        state.performance.onStage = .strokes(id: "s1", strokes: [stroke])

        let result = engine.tick(state: state)
        guard case let .strokeProgressBatch(_, style) = result.events.first else {
            Issue.record("expected a strokeProgressBatch as the first event")
            return
        }
        #expect(style == PartialStrokeStyle(color: "#abcdef", strokeWidth: nil, opacity: nil))
    }

    @Test("leading batch has no style override when the path sets none")
    func leadingBatchNoStyleWhenUnset() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let stroke = PendingStroke(
            batchId: 1,
            path: Path(type: .line, points: [Point(x: 0, y: 0)]),
            points: [Point(x: 0, y: 0), Point(x: 5, y: 0)]
        )
        var state = StudioState()
        state.performance.onStage = .strokes(id: "s1", strokes: [stroke])

        let result = engine.tick(state: state)
        guard case let .strokeProgressBatch(_, style) = result.events.first else {
            Issue.record("expected a strokeProgressBatch as the first event")
            return
        }
        #expect(style == nil)
    }

    // MARK: - §11.2 words item, §5.5 ENQUEUE_WORDS chunk merge

    @Test("words-chunk merge (§5.5) reveals at wordDelayMs cadence across the whole merged chunk")
    func wordsChunkMergeRevealTiming() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        var state = StudioState()
        // Two ENQUEUE_WORDS events for a short chunk merge into a single buffered item
        // (StudioReducer §5.5: merges while the running chunk is under MAX_WORDS_PER_CHUNK).
        state = StudioReducer.reduce(state, .enqueueWords("hello "))
        state = StudioReducer.reduce(state, .enqueueWords("brave new world"))
        #expect(state.performance.buffer.count == 1)
        guard case let .words(_, mergedText) = state.performance.buffer[0] else {
            Issue.record("expected a merged words item")
            return
        }
        #expect(mergedText == "hello brave new world")
        let totalWords = mergedText.split(separator: " ").count
        #expect(totalWords == 4)

        // Advance to stage.
        let advance = engine.tick(state: state)
        #expect(advance.events == [.advanceStage])
        state = StudioReducer.reduce(state, .advanceStage)

        var revealedCounts: [Int] = []
        for _ in 0 ..< totalWords {
            // The first word of a freshly-staged item reveals immediately (no prior
            // reveal recorded); subsequent words are paced at wordDelayMs.
            var result = engine.tick(state: state)
            while result.events.isEmpty {
                clock.advance(by: PerformerConstants.wordDelayMS / 1000)
                result = engine.tick(state: state)
            }
            #expect(result.events == [.revealWord])
            state = StudioReducer.reduce(state, .revealWord)
            revealedCounts.append(state.performance.wordIndex)
        }

        #expect(revealedCounts == Array(1 ... totalWords))
        #expect(state.performance.revealedText == mergedText)

        // All words revealed: must hold for HOLD_AFTER_WORDS_MS before completing.
        let tooSoon = engine.tick(state: state)
        #expect(tooSoon.events.isEmpty)
        clock.advance(by: PerformerConstants.holdAfterWordsMS / 1000)
        let held = engine.tick(state: state)
        #expect(held.events == [.stageComplete])
    }

    // MARK: - §11.3 event item hold timing

    @Test("event item holds for HOLD_EVENT_MS then completes only once the buffer has more work")
    func eventHoldWaitsForBufferedWork() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let message = AgentMessage(id: "m1", type: .codeExecution, text: "running", timestamp: 0)
        var state = StudioState()
        state.performance.onStage = .event(id: "m1", message: message)

        // The hold timer starts counting from the first tick that observes this
        // event on stage, not from an arbitrary wall-clock instant.
        let firstLook = engine.tick(state: state)
        #expect(firstLook.events.isEmpty)

        clock.advance(by: PerformerConstants.holdEventMS / 1000)
        let stillEmpty = engine.tick(state: state)
        #expect(stillEmpty.events.isEmpty) // held minimum time, but nothing buffered yet

        state.performance.buffer = [.words(id: "w1", text: "go")]
        let advances = engine.tick(state: state)
        #expect(advances.events == [.stageComplete])
    }

    @Test("event item force-advances after MAX_EVENT_HOLD_MS even with nothing buffered")
    func eventHoldForceAdvancesWhenStale() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let message = AgentMessage(id: "m1", type: .codeExecution, text: "running", timestamp: 0)
        var state = StudioState()
        state.performance.onStage = .event(id: "m1", message: message)

        let firstLook = engine.tick(state: state)
        #expect(firstLook.events.isEmpty)

        clock.advance(by: PerformerConstants.maxEventHoldMS / 1000)
        let result = engine.tick(state: state)
        #expect(result.events == [.stageComplete])
    }

    // MARK: - §11.7 idle-particle gate, confirmed against this playback loop

    @Test("shouldShowIdleAnimation flips false the instant the first stroke batch lands, per §11.7")
    func idleAnimationGateMatchesPlaybackLoop() {
        let clock = ManualPerformerClock()
        let engine = PerformerEngine(clock: clock)
        let stroke = PendingStroke(
            batchId: 1,
            path: Path(type: .line, points: [Point(x: 0, y: 0), Point(x: 50, y: 0)]),
            points: [Point(x: 0, y: 0), Point(x: 50, y: 0)]
        )
        var state = StudioState()
        state.performance.buffer = [.strokes(id: "s1", strokes: [stroke])]

        #expect(StudioSelectors.shouldShowIdleAnimation(state))

        let advance = engine.tick(state: state)
        state = StudioReducer.reduce(state, .advanceStage)
        #expect(advance.events == [.advanceStage])
        #expect(StudioSelectors.shouldShowIdleAnimation(state)) // staged, but pen hasn't moved yet

        let drawResult = engine.tick(state: state)
        guard case .strokeProgressBatch = drawResult.events.first else {
            Issue.record("expected the pen to start drawing on this tick")
            return
        }
        for event in drawResult.events { state = StudioReducer.reduce(state, event) }
        #expect(!StudioSelectors.shouldShowIdleAnimation(state))
    }
}
