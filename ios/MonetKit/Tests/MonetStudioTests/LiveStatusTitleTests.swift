import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

/// `turn_state` / `init.turn_active` / `piece_title`: decoding, the
/// idle→thinking status rule, and the server title as the single authority.
@Suite("Live status and title")
struct LiveStatusTitleTests {
    private let environment = RoutingEnvironment(now: { 0 }, nextID: { "id" })

    private func route(_ message: ServerMessage, _ state: StudioState) -> StudioState {
        MessageRouter.route(message, environment: environment).reduce(state, StudioReducer.reduce)
    }

    private func decode(_ json: String) throws -> ServerMessage {
        try JSONDecoder().decode(ServerMessage.self, from: Data(json.utf8))
    }

    private static let styleConfigJSON = """
        {"type":"paint","name":"Paint","description":"d",
         "agent_stroke":{"color":"#000","stroke_width":8,"opacity":0.85,"stroke_linecap":"round","stroke_linejoin":"round"},
         "human_stroke":{"color":"#000","stroke_width":8,"opacity":0.85,"stroke_linecap":"round","stroke_linejoin":"round"},
         "supports_color":true,"supports_variable_width":true,"supports_opacity":true,"color_palette":null}
        """

    private func initJSON(_ extra: String) -> String {
        """
        {"type": "init", "strokes": [], "gallery": [], "status": "idle", "paused": false,
         "piece_number": 4, "canvas_width": 800, "canvas_height": 600, "monologue": "",
         "drawing_style": "paint", "style_config": \(Self.styleConfigJSON),
         "painting": null\(extra)}
        """
    }

    // MARK: - Decoding

    @Test("decodes turn_state and piece_title")
    func decodesNewMessages() throws {
        #expect(try decode(#"{"type": "turn_state", "active": true}"#) == .turnState(active: true))
        #expect(try decode(#"{"type": "turn_state", "active": false}"#) == .turnState(active: false))
        #expect(try decode(#"{"type": "piece_title", "piece_number": 4, "title": "Dusk"}"#)
            == .pieceTitle(pieceNumber: 4, title: "Dusk"))
        // Unknown types stay tolerant.
        #expect(try decode(#"{"type": "future_thing", "x": 1}"#) == .unknown(type: "future_thing"))
    }

    @Test("init decodes turn_active; absent reads as false")
    func initTurnActive() throws {
        guard case let .initial(active) = try decode(initJSON(#", "turn_active": true"#)),
              case let .initial(absent) = try decode(initJSON("")) else {
            Issue.record("expected .initial")
            return
        }
        #expect(active.turnActive)
        #expect(!absent.turnActive)
        #expect(StudioReducer.reduce(StudioState(), .initialize(active)).turnActive)
        #expect(!StudioReducer.reduce(StudioState(), .initialize(absent)).turnActive)
    }

    // MARK: - Status rule

    @Test("an active turn turns idle into thinking; turn_state false restores idle")
    func idleBecomesThinking() {
        var state = StudioState()
        state.paused = false
        #expect(StudioSelectors.agentStatus(state) == .idle)
        state = route(.turnState(active: true), state)
        #expect(state.turnActive)
        #expect(StudioSelectors.agentStatus(state) == .thinking)
        state = route(.turnState(active: false), state)
        #expect(StudioSelectors.agentStatus(state) == .idle)
    }

    @Test("paused and error still win over an active turn; real activity keeps its status")
    func priorityKept() {
        var state = StudioState()
        state.turnActive = true
        #expect(StudioSelectors.agentStatus(state) == .paused)
        state.paused = false
        state.messages = [AgentMessage(id: "e", type: .error, text: "boom", timestamp: 0)]
        #expect(StudioSelectors.agentStatus(state) == .error)
        state.messages = []
        state.painting = PaintingState(
            base: nil,
            playing: PaintingVersionRef(pieceNumber: 1, version: 1, assetBase: "/a/", imageWidth: 1, imageHeight: 1)
        )
        #expect(StudioSelectors.agentStatus(state) == .drawing)
    }

    // MARK: - Title

    @Test("piece_title sets the title for the current piece and ignores other pieces")
    func pieceTitleMatching() {
        var state = StudioState()
        state.pieceNumber = 4
        state = route(.pieceTitle(pieceNumber: 3, title: "Old piece"), state)
        #expect(state.title == nil)
        state = route(.pieceTitle(pieceNumber: 4, title: "  Poplars at dusk "), state)
        #expect(state.title == "Poplars at dusk")
    }

    @Test("a completed name_piece tool call no longer sets the title")
    func namePieceToolCallIgnored() {
        let input = JSONValue.object(["title": .string("Poplars at dusk")])
        let completed = CodeExecutionPayload(
            status: .completed, toolName: "name_piece", toolInput: input, stdout: nil, stderr: nil, returnCode: 0, iteration: 1
        )
        var state = StudioState()
        state.pieceNumber = 4
        state = route(.codeExecution(completed), state)
        #expect(state.title == nil)
    }
}
