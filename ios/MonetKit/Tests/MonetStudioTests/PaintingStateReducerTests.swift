import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

/// Mirrors every case in `web/src/test/paintingReducer.test.ts`
/// (program-painting spec §4.1, §8 "Supplementary: reducer/state-machine
/// tests to also mirror").
@Suite("StudioReducer painting")
struct PaintingStateReducerTests {
    private func ref(piece: Int, version: Int, base: String = "/painting-assets/u/t/") -> PaintingVersionRef {
        PaintingVersionRef(pieceNumber: piece, version: version, assetBase: base, imageWidth: 1600, imageHeight: 1200)
    }

    @Test("first version over blank base; drawing status; idle animation hidden")
    func firstVersionOverBlank() {
        var state = StudioState()
        state.pieceNumber = 1
        state.paused = false
        let next = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        #expect(next.painting.base == nil)
        #expect(next.painting.playing == ref(piece: 1, version: 1))
        #expect(StudioSelectors.agentStatus(next) == .drawing)
        #expect(StudioSelectors.shouldShowIdleAnimation(next) == false)
        state = next
    }

    @Test("PAINTING_PLAYBACK_DONE promotes playing to base; status becomes idle")
    func playbackDonePromotes() {
        var state = StudioState()
        state.pieceNumber = 1
        state.paused = false
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        let done = StudioReducer.reduce(state, .paintingPlaybackDone(assetBase: "/painting-assets/u/t/"))
        #expect(done.painting.base == ref(piece: 1, version: 1))
        #expect(done.painting.playing == nil)
        #expect(StudioSelectors.agentStatus(done) == .idle)
    }

    @Test("PAINTING_PLAYBACK_DONE for a non-matching assetBase is a pure no-op")
    func playbackDoneStaleIsNoOp() {
        var state = StudioState()
        state.pieceNumber = 1
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        let result = StudioReducer.reduce(state, .paintingPlaybackDone(assetBase: "/painting-assets/other/token/"))
        #expect(result == state)
    }

    @Test("a second version for the same piece while the first is playing settles it into base")
    func secondVersionSettlesFirst() {
        var state = StudioState()
        state.pieceNumber = 1
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 2)))
        #expect(state.painting.base == ref(piece: 1, version: 1))
        #expect(state.painting.playing == ref(piece: 1, version: 2))
    }

    @Test("duplicate or strictly-older version numbers for the same piece are no-ops")
    func duplicateOrOlderVersionIsNoOp() {
        var state = StudioState()
        state.pieceNumber = 1
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 2)))
        state = StudioReducer.reduce(state, .paintingPlaybackDone(assetBase: "/painting-assets/u/t/"))
        let afterSettle = state

        let dup = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 2)))
        #expect(dup == afterSettle)

        let older = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        #expect(older == afterSettle)
    }

    @Test("a version for an older piece number is a no-op")
    func olderPieceIsNoOp() {
        var state = StudioState()
        state.pieceNumber = 5
        state.painting = PaintingState(base: ref(piece: 5, version: 1), playing: nil)
        let result = StudioReducer.reduce(state, .paintingVersion(ref(piece: 4, version: 1)))
        #expect(result == state)
    }

    @Test("a version received while viewingPiece != nil is a no-op")
    func viewingGalleryDropsVersion() {
        var state = StudioState()
        state.pieceNumber = 1
        state.viewingPiece = 1
        let result = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        #expect(result == state)
    }

    @Test("a version for a newer piece number bumps pieceNumber and drops the old base to nil")
    func newerPieceResetsBase() {
        var state = StudioState()
        state.pieceNumber = 1
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        state = StudioReducer.reduce(state, .paintingPlaybackDone(assetBase: "/painting-assets/u/t/"))
        #expect(state.painting.base != nil)

        let next = StudioReducer.reduce(state, .paintingVersion(ref(piece: 2, version: 1)))
        #expect(next.pieceNumber == 2)
        #expect(next.painting.base == nil)
        #expect(next.painting.playing == ref(piece: 2, version: 1))
    }

    @Test("CLEAR resets painting to blank")
    func clearResetsPainting() {
        var state = StudioState()
        state.pieceNumber = 1
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        let cleared = StudioReducer.reduce(state, .clear)
        #expect(cleared.painting == PaintingState())
    }

    @Test("INIT with a painting ref sets base with no animation; a later INIT with none clears it")
    func initSetsAndClearsPainting() {
        let payload = InitPayload(
            strokes: [], gallery: [], status: "idle", paused: true, pieceNumber: 1,
            canvasWidth: 800, canvasHeight: 600, monologue: "", drawingStyle: .paint,
            styleConfig: .paint, painting: ref(piece: 1, version: 3)
        )
        let initialized = StudioReducer.reduce(StudioState(), .initialize(payload))
        #expect(initialized.painting.base == ref(piece: 1, version: 3))
        #expect(initialized.painting.playing == nil)

        let payloadNoPainting = InitPayload(
            strokes: [], gallery: [], status: "idle", paused: true, pieceNumber: 1,
            canvasWidth: 800, canvasHeight: 600, monologue: "", drawingStyle: .paint,
            styleConfig: .paint, painting: nil
        )
        let reinitialized = StudioReducer.reduce(initialized, .initialize(payloadNoPainting))
        #expect(reinitialized.painting == PaintingState())
    }

    @Test("entering gallery view hides live painting; exiting restores it already-settled")
    func galleryViewHidesAndRestoresSettled() {
        var state = StudioState()
        state.pieceNumber = 1
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        #expect(state.painting.playing != nil)

        let viewing = StudioReducer.reduce(
            state,
            .loadCanvas(LoadCanvasPayload(strokes: [], pieceNumber: 99, canvasWidth: 800, canvasHeight: 600, drawingStyle: nil, styleConfig: nil))
        )
        #expect(viewing.painting == PaintingState())
        #expect(viewing.savedCanvas?.painting.base == ref(piece: 1, version: 1))
        #expect(viewing.savedCanvas?.painting.playing == nil)

        let restored = StudioReducer.reduce(viewing, .clearViewing)
        #expect(restored.painting.base == ref(piece: 1, version: 1))
        #expect(restored.painting.playing == nil)
    }

    @Test("message routing: painting_version dispatches PAINTING_VERSION with stages stripped")
    func messageRoutingStripsStages() {
        let environment = RoutingEnvironment(now: { 0 }, nextID: { "id" })
        let events = MessageRouter.route(.paintingVersion(ref(piece: 1, version: 1), stages: ["ground", "sky"]), environment: environment)
        #expect(events == [.paintingVersion(ref(piece: 1, version: 1))])
    }

    @Test("message routing: init.painting flows into the INIT action's painting field")
    func messageRoutingInitCarriesPainting() {
        let payload = InitPayload(
            strokes: [], gallery: [], status: "idle", paused: true, pieceNumber: 1,
            canvasWidth: 800, canvasHeight: 600, monologue: "", drawingStyle: .paint,
            styleConfig: .paint, painting: ref(piece: 1, version: 1)
        )
        let environment = RoutingEnvironment(now: { 0 }, nextID: { "id" })
        let events = MessageRouter.route(.initial(payload), environment: environment)
        #expect(events == [.initialize(payload)])
    }

    @Test("new_canvas clears painting")
    func newCanvasClearsPainting() {
        var state = StudioState()
        state.pieceNumber = 1
        state = StudioReducer.reduce(state, .paintingVersion(ref(piece: 1, version: 1)))
        let environment = RoutingEnvironment(now: { 0 }, nextID: { "id" })
        let events = MessageRouter.route(.newCanvas(savedID: nil, canvasWidth: 800, canvasHeight: 600), environment: environment)
        var next = state
        for event in events { next = StudioReducer.reduce(next, event) }
        #expect(next.painting == PaintingState())
    }
}
