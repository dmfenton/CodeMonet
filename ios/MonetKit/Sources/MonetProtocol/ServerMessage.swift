import Foundation

/// The one-time full-state snapshot sent to a socket right after connect
/// (protocol-state spec §1.3, §2.2). Not a Pydantic model server-side and
/// not part of the `ServerMessage` union on the wire — decoded by hand here
/// for the same reason.
public struct InitPayload: Codable, Equatable, Sendable {
    public var strokes: [Path]
    public var gallery: [GalleryEntry]
    /// Decoded and intentionally discarded by the reducer — the client
    /// derives its own status rather than trusting the server's (see
    /// `MonetStudio`'s `AgentStatus` selector).
    public var status: String
    public var paused: Bool
    public var pieceNumber: Int
    public var canvasWidth: Int
    public var canvasHeight: Int
    /// Decoded and intentionally discarded (protocol-state spec §9 dead
    /// fields) — kept on the type for fidelity/debuggability only.
    public var monologue: String
    public var drawingStyle: DrawingStyleType
    public var styleConfig: DrawingStyleConfig

    enum CodingKeys: String, CodingKey {
        case strokes, gallery, status, paused
        case pieceNumber = "piece_number"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
        case monologue
        case drawingStyle = "drawing_style"
        case styleConfig = "style_config"
    }

    public init(
        strokes: [Path],
        gallery: [GalleryEntry],
        status: String,
        paused: Bool,
        pieceNumber: Int,
        canvasWidth: Int,
        canvasHeight: Int,
        monologue: String,
        drawingStyle: DrawingStyleType,
        styleConfig: DrawingStyleConfig
    ) {
        self.strokes = strokes
        self.gallery = gallery
        self.status = status
        self.paused = paused
        self.pieceNumber = pieceNumber
        self.canvasWidth = canvasWidth
        self.canvasHeight = canvasHeight
        self.monologue = monologue
        self.drawingStyle = drawingStyle
        self.styleConfig = styleConfig
    }
}

public struct LoadCanvasPayload: Codable, Equatable, Sendable {
    public var strokes: [Path]
    public var pieceNumber: Int
    public var canvasWidth: Int
    public var canvasHeight: Int
    public var drawingStyle: DrawingStyleType
    public var styleConfig: DrawingStyleConfig?

    enum CodingKeys: String, CodingKey {
        case strokes
        case pieceNumber = "piece_number"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
        case drawingStyle = "drawing_style"
        case styleConfig = "style_config"
    }

    public init(
        strokes: [Path],
        pieceNumber: Int,
        canvasWidth: Int,
        canvasHeight: Int,
        drawingStyle: DrawingStyleType,
        styleConfig: DrawingStyleConfig?
    ) {
        self.strokes = strokes
        self.pieceNumber = pieceNumber
        self.canvasWidth = canvasWidth
        self.canvasHeight = canvasHeight
        self.drawingStyle = drawingStyle
        self.styleConfig = styleConfig
    }
}

public struct CodeExecutionPayload: Codable, Equatable, Sendable {
    public var status: ToolExecutionStatus
    public var toolName: String?
    public var toolInput: JSONValue?
    public var stdout: String?
    public var stderr: String?
    public var returnCode: Int?
    public var iteration: Int

    enum CodingKeys: String, CodingKey {
        case status
        case toolName = "tool_name"
        case toolInput = "tool_input"
        case stdout, stderr
        case returnCode = "return_code"
        case iteration
    }

    public init(
        status: ToolExecutionStatus,
        toolName: String?,
        toolInput: JSONValue?,
        stdout: String?,
        stderr: String?,
        returnCode: Int?,
        iteration: Int
    ) {
        self.status = status
        self.toolName = toolName
        self.toolInput = toolInput
        self.stdout = stdout
        self.stderr = stderr
        self.returnCode = returnCode
        self.iteration = iteration
    }
}

/// The full server -> client wire vocabulary, as a discriminated union keyed
/// on the JSON `type` field (protocol-state spec §2.1). An unrecognized
/// `type` decodes to `.unknown` — it is logged, never a crash and never a
/// thrown decode error, since the server's message catalog can grow
/// independently of an installed app.
public enum ServerMessage: Equatable, Sendable {
    case initial(InitPayload)
    case humanStroke(Path)
    case thinkingDelta(text: String, iteration: Int)
    case paused(Bool)
    case clear
    case newCanvas(savedID: String?, canvasWidth: Int, canvasHeight: Int)
    case galleryUpdate([GalleryEntry])
    case loadCanvas(LoadCanvasPayload)
    case codeExecution(CodeExecutionPayload)
    case error(message: String, details: String?)
    case pieceState(number: Int, completed: Bool)
    case iteration(current: Int, max: Int)
    case agentStrokesReady(count: Int, batchID: Int, pieceNumber: Int)
    /// Any `type` this build doesn't recognize. Carries the raw type string
    /// so a caller can at least log what arrived.
    case unknown(type: String)
}

extension ServerMessage: Decodable {
    private enum TypeKey: String, CodingKey { case type }

    public init(from decoder: Decoder) throws {
        let typeContainer = try decoder.container(keyedBy: TypeKey.self)
        let type = try typeContainer.decode(String.self, forKey: .type)
        switch type {
        case "init":
            self = .initial(try InitPayload(from: decoder))
        case "human_stroke":
            self = .humanStroke(try HumanStrokeEnvelope(from: decoder).path)
        case "thinking_delta":
            let envelope = try ThinkingDeltaEnvelope(from: decoder)
            self = .thinkingDelta(text: envelope.text, iteration: envelope.iteration ?? 1)
        case "paused":
            self = .paused(try PausedEnvelope(from: decoder).paused)
        case "clear":
            self = .clear
        case "new_canvas":
            let envelope = try NewCanvasEnvelope(from: decoder)
            self = .newCanvas(
                savedID: envelope.savedID,
                canvasWidth: envelope.canvasWidth ?? CanvasDefaults.width,
                canvasHeight: envelope.canvasHeight ?? CanvasDefaults.height
            )
        case "gallery_update":
            self = .galleryUpdate(try GalleryUpdateEnvelope(from: decoder).canvases)
        case "load_canvas":
            self = .loadCanvas(try LoadCanvasPayload(from: decoder))
        case "code_execution":
            self = .codeExecution(try CodeExecutionPayload(from: decoder))
        case "error":
            let envelope = try ErrorEnvelope(from: decoder)
            self = .error(message: envelope.message, details: envelope.details)
        case "piece_state":
            let envelope = try PieceStateEnvelope(from: decoder)
            self = .pieceState(number: envelope.number, completed: envelope.completed)
        case "iteration":
            let envelope = try IterationEnvelope(from: decoder)
            self = .iteration(current: envelope.current, max: envelope.max ?? 5)
        case "agent_strokes_ready":
            let envelope = try AgentStrokesReadyEnvelope(from: decoder)
            self = .agentStrokesReady(
                count: envelope.count,
                batchID: envelope.batchID,
                pieceNumber: envelope.pieceNumber
            )
        default:
            self = .unknown(type: type)
        }
    }
}

// MARK: - Private per-message decode shims

private struct HumanStrokeEnvelope: Decodable { let path: Path }
private struct ThinkingDeltaEnvelope: Decodable { let text: String; let iteration: Int? }
private struct PausedEnvelope: Decodable { let paused: Bool }
private struct NewCanvasEnvelope: Decodable {
    let savedID: String?
    let canvasWidth: Int?
    let canvasHeight: Int?
    enum CodingKeys: String, CodingKey {
        case savedID = "saved_id"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
    }
}
private struct GalleryUpdateEnvelope: Decodable { let canvases: [GalleryEntry] }
private struct ErrorEnvelope: Decodable { let message: String; let details: String? }
private struct PieceStateEnvelope: Decodable { let number: Int; let completed: Bool }
private struct IterationEnvelope: Decodable { let current: Int; let max: Int? }
private struct AgentStrokesReadyEnvelope: Decodable {
    let count: Int
    let batchID: Int
    let pieceNumber: Int
    enum CodingKeys: String, CodingKey {
        case count
        case batchID = "batch_id"
        case pieceNumber = "piece_number"
    }
}
