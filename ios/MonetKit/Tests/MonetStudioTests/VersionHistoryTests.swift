import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

/// Version history (`StudioState.versions`), title, and prompt: seeding from
/// `init`, session accumulation from `painting_version`, and resets.
@Suite("Version history")
struct VersionHistoryTests {
    private func ref(piece: Int, version: Int) -> PaintingVersionRef {
        PaintingVersionRef(
            pieceNumber: piece, version: version, assetBase: "/painting-assets/u/t\(version)/",
            imageWidth: 1600, imageHeight: 1200
        )
    }

    private func summary(_ version: Int, stages: [String] = [], ops: Int? = nil) -> PaintingVersionSummary {
        PaintingVersionSummary(ref: ref(piece: 1, version: version), stages: stages, ops: ops)
    }

    private func initPayload(
        painting: PaintingVersionRef?,
        versions: [PaintingVersionSummary] = [],
        title: String? = nil,
        prompt: String? = nil
    ) -> InitPayload {
        InitPayload(
            strokes: [], gallery: [], status: "idle", paused: true, pieceNumber: 1,
            canvasWidth: 800, canvasHeight: 600, monologue: "", drawingStyle: .paint, styleConfig: .paint,
            painting: painting, title: title, paintingVersions: versions, prompt: prompt
        )
    }

    private let environment = RoutingEnvironment(now: { 1000 }, nextID: { "id" })

    private func route(_ message: ServerMessage, _ state: StudioState) -> StudioState {
        MessageRouter.route(message, environment: environment).reduce(state, StudioReducer.reduce)
    }

    @Test("init seeds the full history, title, and prompt when the server sends them")
    func initSeedsFromServerHistory() {
        let payload = initPayload(
            painting: ref(piece: 1, version: 2),
            versions: [summary(2, ops: 20), summary(1, ops: 10)],
            title: "Storm",
            prompt: "a stormy sea"
        )
        let state = StudioReducer.reduce(StudioState(), .initialize(payload))
        #expect(state.versions.map(\.version) == [1, 2])
        #expect(state.title == "Storm")
        #expect(state.prompt == "a stormy sea")
        #expect(state.workingVersion == 3)
    }

    @Test("init without history seeds just the current version; no painting seeds nothing")
    func initSeedsFromCurrentVersionOnly() {
        let state = StudioReducer.reduce(StudioState(), .initialize(initPayload(painting: ref(piece: 1, version: 3))))
        #expect(state.versions == [PaintingVersionSummary(ref: ref(piece: 1, version: 3))])
        #expect(state.title == nil)

        let blank = StudioReducer.reduce(StudioState(), .initialize(initPayload(painting: nil)))
        #expect(blank.versions.isEmpty)
        #expect(blank.workingVersion == 1)
    }

    @Test("painting_version accumulates this session's versions with stages and ops")
    func sessionAccumulation() {
        var state = StudioState()
        state.pieceNumber = 1
        state = route(.paintingVersion(ref(piece: 1, version: 1), stages: ["ground"], ops: 100), state)
        state = route(.paintingVersion(ref(piece: 1, version: 2), stages: ["ground", "sky"], ops: 250), state)
        #expect(state.versions == [summary(1, stages: ["ground"], ops: 100), summary(2, stages: ["ground", "sky"], ops: 250)])

        // A duplicate is rejected by the playback guard, so history is unchanged too.
        let duplicate = route(.paintingVersion(ref(piece: 1, version: 2), stages: [], ops: nil), state)
        #expect(duplicate.versions == state.versions)
    }

    @Test("a live version extends an init-seeded history")
    func liveVersionExtendsSeededHistory() {
        var state = StudioReducer.reduce(StudioState(), .initialize(initPayload(
            painting: ref(piece: 1, version: 2), versions: [summary(1), summary(2)]
        )))
        state.paused = false
        state = route(.paintingVersion(ref(piece: 1, version: 3), stages: ["glaze"], ops: 5), state)
        #expect(state.versions.map(\.version) == [1, 2, 3])
        #expect(state.versions.last?.ops == 5)
    }

    @Test("a version for a newer piece starts a fresh history")
    func newPieceResetsHistory() {
        var state = StudioState()
        state.pieceNumber = 1
        state = route(.paintingVersion(ref(piece: 1, version: 1), stages: [], ops: 1), state)
        state = route(.paintingVersion(ref(piece: 2, version: 1), stages: [], ops: 2), state)
        #expect(state.versions.map(\.ops) == [2])
    }

    @Test("clear and new_canvas reset versions, title, and prompt")
    func clearAndNewCanvasReset() {
        var seeded = StudioReducer.reduce(StudioState(), .initialize(initPayload(
            painting: ref(piece: 1, version: 1), versions: [summary(1)], title: "T", prompt: "P"
        )))
        seeded.pieceNumber = 1
        for message in [ServerMessage.clear, .newCanvas(savedID: nil, canvasWidth: 800, canvasHeight: 600)] {
            let next = route(message, seeded)
            #expect(next.versions.isEmpty)
            #expect(next.title == nil)
            #expect(next.prompt == nil)
        }
    }

    @Test("gallery viewing leaves the live piece's history alone")
    func galleryViewingKeepsHistory() {
        var state = StudioState()
        state.pieceNumber = 1
        state = route(.paintingVersion(ref(piece: 1, version: 1), stages: [], ops: nil), state)
        let viewing = StudioReducer.reduce(state, .loadCanvas(LoadCanvasPayload(
            strokes: [], pieceNumber: 9, canvasWidth: 800, canvasHeight: 600, drawingStyle: .paint, styleConfig: nil
        )))
        #expect(viewing.versions == state.versions)
        // Live versions arriving while viewing are dropped by the gallery guard.
        let during = route(.paintingVersion(ref(piece: 1, version: 2), stages: [], ops: nil), viewing)
        #expect(during.versions == state.versions)
        #expect(StudioReducer.reduce(viewing, .clearViewing).versions == state.versions)
    }

    @Test("a completed name_piece call sets the title; a failed one doesn't")
    func namePieceSetsTitle() {
        let input = JSONValue.object(["title": .string("  Poplars at dusk ")])
        let started = CodeExecutionPayload(
            status: .started, toolName: "name_piece", toolInput: input, stdout: nil, stderr: nil, returnCode: nil, iteration: 1
        )
        var completed = started
        completed.status = .completed
        completed.returnCode = 0
        var state = route(.codeExecution(started), StudioState())
        #expect(state.title == nil)
        state = route(.codeExecution(completed), state)
        #expect(state.title == "Poplars at dusk")

        var failed = completed
        failed.returnCode = 1
        #expect(route(.codeExecution(failed), StudioState()).title == nil)
    }

    @Test("title fallback: title, then truncated prompt, then Piece N")
    func titleFallback() {
        #expect(PieceTitle.resolve(title: "Lilies", prompt: "p", pieceNumber: 3) == "Lilies")
        #expect(PieceTitle.resolve(title: "  ", prompt: "a small pond", pieceNumber: 3) == "a small pond")
        let long = "a small pond with lilies at dusk, reflections trembling under willows"
        let resolved = PieceTitle.resolve(title: nil, prompt: long, pieceNumber: 3)
        #expect(resolved.hasSuffix("…"))
        #expect(resolved.count <= PieceTitle.maxPromptLength + 1)
        #expect(long.hasPrefix(String(resolved.dropLast())))
        #expect(PieceTitle.resolve(title: nil, prompt: nil, pieceNumber: 3) == "Piece 3")
    }
}
