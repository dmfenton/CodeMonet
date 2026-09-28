import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

/// Mirrors `describe('live painting')` in `web/src/test/paintingReducer.test.ts`
/// (docs/program-painting.md "WebSocket": `painting_live`,
/// `painting_live_failed`, `init.painting_live`).
@Suite("StudioReducer live painting")
struct LivePaintingReducerTests {
    private func ref(_ piece: Int, _ version: Int) -> PaintingVersionRef {
        PaintingVersionRef(
            pieceNumber: piece, version: version, assetBase: "/painting-assets/u/p\(piece)v\(version)/",
            imageWidth: 1600, imageHeight: 1200
        )
    }

    private func liveRef(_ piece: Int, _ version: Int) -> PaintingLiveRef {
        let full = ref(piece, version)
        return PaintingLiveRef(
            pieceNumber: full.pieceNumber, assetBase: full.assetBase, imageWidth: full.imageWidth, imageHeight: full.imageHeight
        )
    }

    private func reduce(_ state: StudioState, _ events: StudioEvent...) -> StudioState {
        events.reduce(state, StudioReducer.reduce)
    }

    /// Piece 3 with v1 played and settled.
    private var withBase: StudioState {
        var state = StudioState()
        state.pieceNumber = 3
        state.paused = false
        return reduce(state, .paintingVersion(ref(3, 1)), .paintingPlaybackDone(assetBase: ref(3, 1).assetBase))
    }

    @Test("plays a run live over the current picture")
    func playsLiveOverBase() {
        let state = reduce(withBase, .paintingLive(liveRef(3, 2)))
        #expect(state.painting == PaintingState(base: ref(3, 1), live: LivePainting(ref: liveRef(3, 2))))
        #expect(StudioSelectors.agentStatus(state) == .drawing)
        #expect(StudioSelectors.shouldShowIdleAnimation(state) == false)
    }

    @Test("confirms the run without replaying it, then settles when playback ends")
    func confirmsThenSettles() {
        let state = reduce(withBase, .paintingLive(liveRef(3, 2)), .paintingVersion(ref(3, 2), stages: ["sky"], ops: 9))
        #expect(state.painting.playing == nil)
        #expect(state.painting.live?.confirmed == ref(3, 2))
        #expect(state.versions.map(\.version) == [1, 2])
        #expect(state.versions.last?.ops == 9)
        let done = reduce(state, .paintingLiveDone(assetBase: ref(3, 2).assetBase))
        #expect(done.painting == PaintingState(base: ref(3, 2)))
        #expect(StudioSelectors.agentStatus(done) == .idle)
    }

    @Test("settles on confirmation when playback finished first")
    func settlesOnConfirmationAfterPlayback() {
        let played = reduce(withBase, .paintingLive(liveRef(3, 2)), .paintingLiveDone(assetBase: ref(3, 2).assetBase))
        #expect(played.painting.live?.played == true)
        // Played to the end: no longer drawing while waiting on the server.
        #expect(StudioSelectors.agentStatus(played) == .idle)
        let state = reduce(played, .paintingVersion(ref(3, 2)))
        #expect(state.painting == PaintingState(base: ref(3, 2)))
    }

    @Test("rolls back to the previous picture when the run fails")
    func failureRollsBack() {
        let state = reduce(withBase, .paintingLive(liveRef(3, 2)), .paintingLiveFailed(assetBase: ref(3, 2).assetBase))
        #expect(state.painting == PaintingState(base: ref(3, 1)))
        // A stale failure for another run is ignored.
        let live = reduce(withBase, .paintingLive(liveRef(3, 3)))
        #expect(reduce(live, .paintingLiveFailed(assetBase: ref(3, 2).assetBase)) == live)
    }

    @Test("a new run replaces an unconfirmed one")
    func newRunReplacesUnconfirmed() {
        let state = reduce(withBase, .paintingLive(liveRef(3, 2)), .paintingLive(liveRef(3, 3)))
        #expect(state.painting.base == ref(3, 1))
        #expect(state.painting.live?.ref == liveRef(3, 3))
    }

    @Test("a new run settles a confirmed one into the base")
    func newRunSettlesConfirmed() {
        let state = reduce(
            withBase, .paintingLive(liveRef(3, 2)), .paintingVersion(ref(3, 2)), .paintingLive(liveRef(3, 3))
        )
        #expect(state.painting.base == ref(3, 2))
        #expect(state.painting.live?.ref == liveRef(3, 3))
    }

    @Test("a run for a newer piece starts from blank and syncs the piece number")
    func newerPieceStartsBlank() {
        let state = reduce(withBase, .paintingLive(liveRef(4, 1)))
        #expect(state.pieceNumber == 4)
        #expect(state.painting == PaintingState(live: LivePainting(ref: liveRef(4, 1))))
    }

    @Test("routes live messages and ignores them while viewing a gallery piece or for an older piece")
    func routesAndGuards() {
        let environment = RoutingEnvironment(now: { 0 }, nextID: { "id" })
        let started = MessageRouter.route(.paintingLive(liveRef(3, 2)), environment: environment)
        #expect(started == [.paintingLive(liveRef(3, 2))])
        #expect(MessageRouter.route(.paintingLiveFailed(pieceNumber: 3, assetBase: "/a/"), environment: environment)
            == [.paintingLiveFailed(assetBase: "/a/")])
        let state = reduce(withBase, started[0])
        #expect(state.painting.live?.ref == liveRef(3, 2))

        var viewing = withBase
        viewing.viewingPiece = 1
        #expect(reduce(viewing, started[0]) == viewing)
        #expect(reduce(withBase, .paintingLive(liveRef(2, 5))) == withBase)
    }

    @Test("PAINTING_LIVE_DONE for another run is a no-op")
    func staleDoneIsNoOp() {
        let state = reduce(withBase, .paintingLive(liveRef(3, 2)))
        #expect(reduce(state, .paintingLiveDone(assetBase: "/other/")) == state)
    }

    @Test("entering gallery view drops an unconfirmed run and keeps a confirmed one, settled")
    func galleryViewSettlesLive() {
        let load = StudioEvent.loadCanvas(LoadCanvasPayload(
            strokes: [], pieceNumber: 99, canvasWidth: 800, canvasHeight: 600, drawingStyle: nil, styleConfig: nil
        ))
        let unconfirmed = reduce(withBase, .paintingLive(liveRef(3, 2)), load, .clearViewing)
        #expect(unconfirmed.painting == PaintingState(base: ref(3, 1)))
        let confirmed = reduce(withBase, .paintingLive(liveRef(3, 2)), .paintingVersion(ref(3, 2)), load, .clearViewing)
        #expect(confirmed.painting == PaintingState(base: ref(3, 2)))
    }

    @Test("INIT follows a run streaming for this piece that isn't the current version")
    func initSeedsLive() {
        func payload(painting: PaintingVersionRef?, live: PaintingLiveRef?) -> InitPayload {
            InitPayload(
                strokes: [], gallery: [], status: "idle", paused: false, pieceNumber: 3,
                canvasWidth: 800, canvasHeight: 600, monologue: "", drawingStyle: .paint,
                styleConfig: .paint, painting: painting, paintingLive: live
            )
        }
        let joining = reduce(StudioState(), .initialize(payload(painting: ref(3, 1), live: liveRef(3, 2))))
        #expect(joining.painting == PaintingState(base: ref(3, 1), live: LivePainting(ref: liveRef(3, 2))))
        // Already recorded as the current version: nothing to follow.
        let recorded = reduce(StudioState(), .initialize(payload(painting: ref(3, 2), live: liveRef(3, 2))))
        #expect(recorded.painting == PaintingState(base: ref(3, 2)))
        // A run for another piece is not followed.
        let other = reduce(StudioState(), .initialize(payload(painting: nil, live: liveRef(4, 1))))
        #expect(other.painting == PaintingState())
    }
}
