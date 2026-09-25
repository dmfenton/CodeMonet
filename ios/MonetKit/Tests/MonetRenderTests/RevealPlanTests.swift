import Foundation
@testable import MonetProtocol
@testable import MonetRender
import Testing

/// Swift-test parity for `app/src/__tests__/revealPlan.test.ts`
/// (program-painting spec §8). Fixture manifest: 3 keyframes — "ground" (1
/// area op, whole canvas), "empty" (0 ops), "strokes" (2 stroke ops + 1
/// area op). Global op indices: 0 = ground's area op, 1 = strokes-kf's
/// first stroke, 2 = strokes-kf's second stroke (a 1-point dot,
/// `['s', 8, 50, 60]`), 3 = strokes-kf's area op.
@Suite("RevealPlan (revealPlan.test.ts parity)")
struct RevealPlanTests {
    static func makeManifest() -> RevealManifest {
        RevealManifest(
            width: 1600,
            height: 1200,
            keyframes: [
                RevealKeyframe(label: "ground", image: "kf_00.jpg", ops: [
                    .area(x0: 0, y0: 0, x1: 1600, y1: 1200),
                ]),
                RevealKeyframe(label: "empty", image: "kf_01.jpg", ops: []),
                RevealKeyframe(label: "strokes", image: "kf_02.jpg", ops: [
                    .stroke(width: 18.2, points: [Point(x: 100, y: 100), Point(x: 150, y: 120)]),
                    .stroke(width: 8, points: [Point(x: 50, y: 60)]),
                    .area(x0: 0, y0: 0, x1: 100, y1: 100),
                ]),
            ]
        )
    }

    // MARK: - buildRevealPlan

    @Test("flattens ops across keyframes with global indices")
    func flattensGlobalIndices() {
        let plan = buildRevealPlan(Self.makeManifest())
        #expect(plan.opKind == [.area, .stroke, .stroke, .area])
        #expect(plan.keyframes.map { [$0.opStart, $0.opEnd] } == [[0, 1], [1, 1], [1, 4]])
        #expect(plan.keyframes.map(\.image) == ["kf_00.jpg", "kf_01.jpg", "kf_02.jpg"])
    }

    @Test("stores op numbers without the op tag")
    func storesOpDataWithoutTag() {
        let plan = buildRevealPlan(Self.makeManifest())
        #expect(plan.opDataStart.count == plan.opKind.count + 1)
        func slice(_ i: Int) -> [Double] { Array(plan.opData[plan.opDataStart[i] ..< plan.opDataStart[i + 1]]) }
        #expect(slice(0) == [0, 0, 1600, 1200])
        #expect(slice(2) == [8, 50, 60])
    }

    @Test("matches the shared schedule timing")
    func matchesSharedSchedule() {
        let manifest = Self.makeManifest()
        let plan = buildRevealPlan(manifest)
        let schedule = buildRevealSchedule(manifest)
        #expect(plan.totalMs == schedule.totalMs)
        #expect(plan.opEndMs == schedule.keyframes.flatMap(\.opEndMs))
        #expect(plan.keyframes.map { [$0.startMs, $0.endMs] } == schedule.keyframes.map { [$0.startMs, $0.endMs] })
    }

    // MARK: - advanceRevealPlan

    private final class RecordingSink: RevealSink {
        enum Event: Equatable {
            case ops(kf: Int, from: Int, to: Int)
            case settle(kf: Int)
            case wipe(kf: Int, op: Int, progress: Double)
        }
        var events: [Event] = []
        func revealOps(kf: Int, from: Int, to: Int) { events.append(.ops(kf: kf, from: from, to: to)) }
        func settleKeyframe(_ kf: Int) { events.append(.settle(kf: kf)) }
        func wipeArea(kf: Int, op: Int, progress: Double) { events.append(.wipe(kf: kf, op: op, progress: progress)) }
    }

    @Test("wipes an in-flight area op without revealing it")
    func wipesInFlightAreaOp() {
        let plan = buildRevealPlan(Self.makeManifest())
        let sink = RecordingSink()
        var cursor = RevealCursor(kf: 0, op: 0)
        let halfway = plan.opEndMs[0] / 2
        let done = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: halfway, sink: sink)
        #expect(done == false)
        #expect(cursor == RevealCursor(kf: 0, op: 0))
        #expect(sink.events == [.wipe(kf: 0, op: 0, progress: 0.5)])
    }

    @Test("settles completed keyframes, including empty ones, in order")
    func settlesCompletedKeyframesInOrder() {
        let plan = buildRevealPlan(Self.makeManifest())
        let sink = RecordingSink()
        var cursor = RevealCursor(kf: 0, op: 0)
        let done = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: plan.opEndMs[1], sink: sink)
        #expect(done == false)
        #expect(sink.events == [
            .ops(kf: 0, from: 0, to: 1),
            .settle(kf: 0),
            .settle(kf: 1),
            .ops(kf: 2, from: 1, to: 2),
        ])
        #expect(cursor == RevealCursor(kf: 2, op: 2))
    }

    @Test("only emits newly revealed ops on subsequent frames")
    func onlyEmitsNewlyRevealedOps() {
        let plan = buildRevealPlan(Self.makeManifest())
        let sink = RecordingSink()
        var cursor = RevealCursor(kf: 0, op: 0)
        _ = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: plan.opEndMs[1], sink: sink)
        sink.events.removeAll()

        // Same elapsedMs again: idempotent no-op.
        _ = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: plan.opEndMs[1], sink: sink)
        #expect(sink.events.isEmpty)

        // Advance to opEndMs[2]: exactly one new event.
        _ = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: plan.opEndMs[2], sink: sink)
        #expect(sink.events == [.ops(kf: 2, from: 2, to: 3)])
    }

    @Test("agrees with the shared revealProgressAt at every sampled time")
    func agreesWithRevealProgressAt() {
        let manifest = Self.makeManifest()
        let plan = buildRevealPlan(manifest)
        let schedule = buildRevealSchedule(manifest)
        var cursor = RevealCursor()
        let sink = RecordingSink()
        var t: Double = 0
        while t <= plan.totalMs {
            _ = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: t, sink: sink)
            let progress = revealProgressAt(schedule, t)
            switch progress {
            case .done:
                // Only reachable once cursor has walked past every keyframe.
                break
            case let .playing(keyframe, opsDone, _):
                #expect(cursor.kf == keyframe, "at t=\(t)")
                #expect(cursor.op - plan.keyframes[cursor.kf].opStart == opsDone, "at t=\(t)")
            }
            t += 7
        }
    }

    @Test("finishes everything at the end, even when frames were skipped")
    func finishesEverythingAtEndWithSkippedFrames() {
        let plan = buildRevealPlan(Self.makeManifest())
        let sink = RecordingSink()
        var cursor = RevealCursor()
        let done = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: plan.totalMs + 1000, sink: sink)
        #expect(done == true)
        #expect(sink.events == [
            .ops(kf: 0, from: 0, to: 1),
            .settle(kf: 0),
            .settle(kf: 1),
            .ops(kf: 2, from: 1, to: 4),
            .settle(kf: 2),
        ])
    }

    @Test("is done immediately for a manifest without ops")
    func doneImmediatelyForEmptyManifest() {
        let manifest = RevealManifest(width: 100, height: 100, keyframes: [
            RevealKeyframe(label: "only", image: "kf_00.jpg", ops: []),
        ])
        let plan = buildRevealPlan(manifest)
        let sink = RecordingSink()
        var cursor = RevealCursor()
        let done = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: 0, sink: sink)
        #expect(done == true)
        #expect(sink.events == [.settle(kf: 0)])
    }

    // MARK: - Gallery raster URLs

    @Test("joins API-relative paths onto the API base")
    func joinsApiRelativePaths() {
        #expect(
            PaintingAssetURL.apiAssetUrl("http://localhost:8000", "/painting-assets/u/t/final.png")
                == "http://localhost:8000/painting-assets/u/t/final.png"
        )
        #expect(
            PaintingAssetURL.apiAssetUrl("https://monet.dmfenton.net/api/", "/painting-assets/x")
                == "https://monet.dmfenton.net/api/painting-assets/x"
        )
        #expect(
            PaintingAssetURL.apiAssetUrl("http://a", "https://cdn/x.png") == "https://cdn/x.png"
        )
    }

    @Test("only resolves raster pieces with an image_url")
    func onlyResolvesRasterWithImageURL() {
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .strokes, imageURL: "/x.png") == nil)
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .raster, imageURL: nil) == nil)
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .other(""), imageURL: "/x.png") == nil)
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .raster, imageURL: "/x.png") == "http://a/x.png")
    }
}
