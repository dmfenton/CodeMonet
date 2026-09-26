import MonetProtocol

/// Non-reducer inputs a caller must supply so `MessageRouter.route` can stay
/// deterministic and testable: current wall-clock time (epoch ms, matching
/// `AgentMessage.timestamp`) and a fresh id generator for newly-synthesized
/// `AgentMessage`s. Production code wires this to `Date()`/`UUID()`; tests
/// wire it to fixed values.
public struct RoutingEnvironment: Sendable {
    public var now: @Sendable () -> Double
    public var nextID: @Sendable () -> String

    public init(now: @escaping @Sendable () -> Double, nextID: @escaping @Sendable () -> String) {
        self.now = now
        self.nextID = nextID
    }
}

/// Result of routing one `agent_strokes_ready` message (protocol-state spec
/// §6.2). This message never turns directly into `StudioEvent`s — its data
/// only reaches state via a REST fetch (`GET /strokes/pending`) that the
/// networking/store layer orchestrates. `MessageRouter` surfaces the intent
/// (with the three guards already applied) so that layer doesn't have to
/// re-derive them.
public struct StrokesReadySignal: Equatable, Sendable {
    public var batchID: Int
    public var pieceNumber: Int
    /// Non-nil when the piece-sync guard fired: dispatch this first.
    public var pieceNumberSyncEvent: StudioEvent?
}

/// Translates one `ServerMessage` into zero or more `StudioEvent`s
/// (protocol-state spec §6.1's `routeMessage` dispatch table). This is a
/// separate, impure layer above the pure `StudioReducer` — it is where
/// `AgentMessage`s get their id/timestamp and where tool-name -> label/icon
/// text is resolved.
public enum MessageRouter {
    /// Routes every `ServerMessage` case *except* `.agentStrokesReady`,
    /// which has no reducer-event mapping at all (protocol-state spec §6.1:
    /// confirmed zero dispatched actions) — use `routeStrokesReady` for that
    /// one, applying its three guards against the *current* state first.
    public static func route(
        _ message: ServerMessage,
        environment: RoutingEnvironment
    ) -> [StudioEvent] {
        switch message {
        case let .initial(payload):
            return [.initialize(payload)]
        case let .humanStroke(path):
            // Self-echo decision (protocol-state spec §7.1): the RN app
            // dispatches an OPTIMISTIC local `ADD_STROKE` when a human
            // finishes a touch-stroke, then sends `{type:"stroke"}` to the
            // server. Because `UserConnectionManager.broadcast` doesn't
            // exclude the sender, the server's `human_stroke` reply lands
            // back on the same socket and gets added a *second* time — every
            // human-drawn stroke on the drawing device is double-counted.
            //
            // Fix, not port: `MessageRouter.route(.humanStroke)` is the
            // ONLY place a human-authored `Path` is appended to
            // `StudioState.strokes` (this line). The Swift caller
            // (`StudioStore.endStroke()`, package 4) sends `.stroke(points:)`
            // to the server and does NOT dispatch `.addStroke` itself first —
            // it relies solely on this broadcast echo, so the duplicate is
            // never created rather than being created-then-deduped. This is
            // strictly simpler than tracking "pending self-sent stroke
            // signatures" (the spec's other suggested fix) and produces the
            // identical end state: `Path` is `Equatable`, so if a future
            // caller adds optimistic local rendering for lower perceived
            // latency, it must render through transient state
            // (`currentStroke/performance.agentStroke`-style), not by
            // appending directly to `strokes` — or it must dedupe by exact
            // `Path` equality against a tracked pending-echo set before this
            // event is applied, to preserve the "each stroke appended
            // exactly once" invariant this function relies on.
            //
            // Multi-connection decision (protocol-state spec §7.2):
            // `human_stroke` (and `load_canvas`, and the rate-limit `error`)
            // are broadcast to every one of the user's connections, not just
            // the sender — "your account, your canvas, synced everywhere".
            // `MonetStudio` makes no attempt to distinguish "my device sent
            // this" from "another of my devices sent this": every inbound
            // message is processed identically regardless of origin, which
            // is the correct behavior for that product decision (kept, not
            // scoped down) and requires no extra state here.
            return [.addStroke(path)]
        case let .thinkingDelta(text, _):
            return [.enqueueWords(text), .appendThinking(text)]
        case let .paused(paused):
            return [.setPaused(paused)]
        case .clear:
            return [.clearPerformance, .clear, .clearMessages]
        case let .newCanvas(_, width, height):
            return [.clearPerformance, .setCanvasSize(width: width, height: height), .clear, .clearMessages]
        case let .galleryUpdate(canvases):
            return [.setGallery(canvases)]
        case let .loadCanvas(payload):
            return [.loadCanvas(payload)]
        case let .codeExecution(payload):
            let message = ToolLabels.agentMessage(for: payload, id: environment.nextID(), timestamp: environment.now())
            return [.enqueueEvent(message), .addMessage(message)]
        case let .error(text, details):
            let message = AgentMessage(
                id: environment.nextID(),
                type: .error,
                text: text,
                timestamp: environment.now(),
                metadata: details.map { AgentMessageMetadata(stderr: $0) }
            )
            return [.archiveThinking(messageID: environment.nextID(), timestamp: environment.now()), .addMessage(message)]
        case let .pieceState(number, completed):
            var events: [StudioEvent] = [.setPieceNumber(number)]
            if completed {
                let message = AgentMessage(
                    id: environment.nextID(),
                    type: .pieceComplete,
                    text: "Piece #\(number) complete!",
                    timestamp: environment.now(),
                    metadata: AgentMessageMetadata(pieceNumber: number)
                )
                events.append(.archiveThinking(messageID: environment.nextID(), timestamp: environment.now()))
                events.append(.addMessage(message))
            }
            return events
        case let .iteration(current, max):
            return [.archiveThinking(messageID: environment.nextID(), timestamp: environment.now()), .setIteration(current: current, max: max)]
        case .agentStrokesReady:
            // Handled by `routeStrokesReady` — never reaches the reducer directly.
            return []
        case let .paintingVersion(ref, _):
            // `stages` is display-only and never reaches reducer state
            // (program-painting spec §4.2) — a UI wanting to show it reads
            // it directly off this `ServerMessage` case, or off a fetched
            // `reveal.json`'s keyframe labels, not from `StudioState`.
            return [.paintingVersion(ref)]
        case .unknown:
            return []
        }
    }

    /// Applies the gallery/stale-piece/piece-sync guards from protocol-state
    /// spec §6.2 to an `agent_strokes_ready` message against `state`. Returns
    /// `nil` when the message should be dropped entirely (viewing a gallery
    /// piece, or the batch is for an older piece than the client is on).
    public static func routeStrokesReady(
        count: Int,
        batchID: Int,
        pieceNumber: Int,
        state: StudioState
    ) -> StrokesReadySignal? {
        guard state.viewingPiece == nil else { return nil }
        guard pieceNumber >= state.pieceNumber else { return nil }
        let sync: StudioEvent? = pieceNumber > state.pieceNumber ? .setPieceNumber(pieceNumber) : nil
        return StrokesReadySignal(batchID: batchID, pieceNumber: pieceNumber, pieceNumberSyncEvent: sync)
    }
}

/// Tool-name -> display copy for `LiveStatus`/`MessageStream` (ux spec §6.1,
/// §6.3). Centralized here (not in a UI target) so both the app's UI layer
/// and any headless tooling agree on the same strings.
public enum ToolLabels {
    public static func startedText(toolName: String?, toolInput: JSONValue?) -> String {
        switch toolName {
        case "draw_paths":
            if let count = pathCount(from: toolInput) {
                return "Drawing \(count) path\(count == 1 ? "" : "s")..."
            }
            return "Drawing paths..."
        case "generate_svg": return "Generating SVG..."
        case "view_canvas": return "Viewing canvas..."
        case "critique_canvas": return "Critiquing canvas..."
        case "mark_piece_done": return "Marking done..."
        case "imagine": return "Imagining..."
        case "sign_canvas": return "Signing..."
        case "name_piece": return "Naming piece..."
        // Program painting (spec §7): rides the pre-existing generic
        // `code_execution` message, not a new wire type — just another
        // `tool_name` value with its own display copy.
        case "paint": return "Painting..."
        default: return "Executing..."
        }
    }

    public static func completedText(toolName: String?, toolInput: JSONValue?, returnCode: Int?) -> String {
        if let returnCode, returnCode != 0 {
            return "\(toolName ?? "Tool") failed (exit \(returnCode))"
        }
        switch toolName {
        case "draw_paths":
            if let count = pathCount(from: toolInput) {
                return "Drew \(count) path\(count == 1 ? "" : "s")"
            }
            return "Paths drawn"
        case "generate_svg": return "SVG generated"
        case "view_canvas": return "Canvas viewed"
        case "critique_canvas": return "Critique complete"
        case "mark_piece_done": return "Marked done"
        case "imagine": return "Imagined"
        case "sign_canvas": return "Signed"
        case "name_piece": return "Piece named"
        case "paint": return "Painted"
        default: return "Done"
        }
    }

    public static func agentMessage(for payload: CodeExecutionPayload, id: String, timestamp: Double) -> AgentMessage {
        let text = payload.status == .started
            ? startedText(toolName: payload.toolName, toolInput: payload.toolInput)
            : completedText(toolName: payload.toolName, toolInput: payload.toolInput, returnCode: payload.returnCode)
        let metadata = AgentMessageMetadata(
            toolName: payload.toolName,
            toolInput: payload.toolInput,
            stdout: payload.stdout,
            stderr: payload.stderr,
            returnCode: payload.returnCode
        )
        return AgentMessage(
            id: id,
            type: .codeExecution,
            text: text,
            timestamp: timestamp,
            iteration: payload.iteration,
            status: payload.status,
            metadata: metadata
        )
    }

    private static func pathCount(from toolInput: JSONValue?) -> Int? {
        guard case let .object(fields)? = toolInput, case let .array(paths)? = fields["paths"] else { return nil }
        return paths.count
    }
}
