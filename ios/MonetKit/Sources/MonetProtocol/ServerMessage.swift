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
    /// The current program-painting version, if any (program-painting spec
    /// §1.2) — omitted-as-null when `WorkspaceState.painting` is `None`
    /// (new piece, plotter mode, or paint mode before the first `paint`
    /// call). Unlike `painting_version`, this ref carries **no `stages`
    /// field**. A client shows this version's `final.png` immediately, with
    /// no reveal animation — `init` never replays history.
    public var painting: PaintingVersionRef?
    /// The current piece's title (additive server field; `nil` until the
    /// agent names the piece, or from a server that doesn't send it).
    public var title: String?
    /// `init.painting.versions`: every version of the current piece, oldest
    /// first. Additive server field — empty when absent, in which case the
    /// client builds its version list from this session's
    /// `painting_version` messages instead.
    public var paintingVersions: [PaintingVersionSummary]
    /// The direction the current piece was started with: top-level
    /// `init.prompt`, else `init.painting.prompt` (both additive fields).
    public var prompt: String?

    enum CodingKeys: String, CodingKey {
        case strokes, gallery, status, paused
        case pieceNumber = "piece_number"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
        case monologue
        case drawingStyle = "drawing_style"
        case styleConfig = "style_config"
        case painting
        case title, prompt
    }

    /// The additive keys `init.painting` may carry beside the ref fields.
    private struct PaintingExtras: Decodable {
        let versions: [PaintingVersionSummary]
        let prompt: String?

        enum CodingKeys: String, CodingKey { case versions, prompt }

        /// Additive fields: a malformed version entry is skipped, and a
        /// wrongly-typed `versions`/`prompt` reads as absent — neither may
        /// fail `init`.
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            versions = (try? container.decodeIfPresent(LossyArray<PaintingVersionSummary>.self, forKey: .versions))?
                .elements ?? []
            prompt = try? container.decodeIfPresent(String.self, forKey: .prompt)
        }
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
        styleConfig: DrawingStyleConfig,
        painting: PaintingVersionRef? = nil,
        title: String? = nil,
        paintingVersions: [PaintingVersionSummary] = [],
        prompt: String? = nil
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
        self.painting = painting
        self.title = title
        self.paintingVersions = paintingVersions
        self.prompt = prompt
    }

    /// Custom decode: `canvas_width`/`canvas_height` are documented as always
    /// sent, but `text_chunking_flow.json` (recorded via the visual-flow-test
    /// harness rather than the SDK-integration recorder) predates that and
    /// omits both keys entirely (confirmed by inspection). Fall back to the
    /// same 800x600 default the server/TS `?? 800`/`?? 600` fallback uses
    /// (protocol-state spec §2.2, §10) instead of throwing on an older
    /// recording.
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        strokes = try container.decode([Path].self, forKey: .strokes)
        gallery = try container.decode([GalleryEntry].self, forKey: .gallery)
        status = try container.decode(String.self, forKey: .status)
        paused = try container.decode(Bool.self, forKey: .paused)
        pieceNumber = try container.decode(Int.self, forKey: .pieceNumber)
        canvasWidth = try container.decodeIfPresent(Int.self, forKey: .canvasWidth) ?? CanvasDefaults.width
        canvasHeight = try container.decodeIfPresent(Int.self, forKey: .canvasHeight) ?? CanvasDefaults.height
        monologue = try container.decode(String.self, forKey: .monologue)
        drawingStyle = try container.decode(DrawingStyleType.self, forKey: .drawingStyle)
        styleConfig = try container.decode(DrawingStyleConfig.self, forKey: .styleConfig)
        painting = try container.decodeIfPresent(PaintingVersionRef.self, forKey: .painting)
        title = try container.decodeIfPresent(String.self, forKey: .title)
        let extras = painting == nil ? nil : try container.decodeIfPresent(PaintingExtras.self, forKey: .painting)
        paintingVersions = extras?.versions ?? []
        prompt = try container.decodeIfPresent(String.self, forKey: .prompt) ?? extras?.prompt
    }
}

/// Protocol-state spec §2.2 documents `drawing_style`/`canvas_width`/
/// `canvas_height` as always present on the wire (server-side Pydantic
/// defaults), but §5.4's *reducer* contract for `LOAD_CANVAS` explicitly
/// treats the action's `drawingStyle` as optional ("`action.drawingStyle ??
/// state.drawingStyle` — keep current if omitted"), unlike `INIT`'s
/// drawing-style handling which is a full reset to `.plotter` when absent.
/// `drawingStyle` is therefore modeled as optional here — decode-tolerant
/// for an older/partial payload, and the reducer applies the spec's
/// keep-current fallback rather than a fixed default (`StudioReducer`'s
/// `.loadCanvas` case).
public struct LoadCanvasPayload: Codable, Equatable, Sendable {
    public var strokes: [Path]
    public var pieceNumber: Int
    public var canvasWidth: Int
    public var canvasHeight: Int
    public var drawingStyle: DrawingStyleType?
    public var styleConfig: DrawingStyleConfig?
    /// `.raster` for a program-painting piece with no vector strokes to
    /// draw — `imageURL` is then where its final image lives (program-
    /// painting spec §2.1's `galleryRasterImageUrl`). Absent from the live
    /// WS `load_canvas` broadcast today (server only ever sends `.strokes`
    /// pieces over it); populated by `StudioStore.applyLoadedGalleryPiece`
    /// from the REST `GET /gallery/{n}/strokes` response, which already
    /// carries both (`GalleryPieceStrokes`). Defaults to `.strokes`/`nil`
    /// so an older/partial payload decodes exactly as before.
    public var format: GalleryPieceFormat
    public var imageURL: String?

    enum CodingKeys: String, CodingKey {
        case strokes
        case pieceNumber = "piece_number"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
        case drawingStyle = "drawing_style"
        case styleConfig = "style_config"
        case format
        case imageURL = "image_url"
    }

    public init(
        strokes: [Path],
        pieceNumber: Int,
        canvasWidth: Int,
        canvasHeight: Int,
        drawingStyle: DrawingStyleType?,
        styleConfig: DrawingStyleConfig?,
        format: GalleryPieceFormat = .strokes,
        imageURL: String? = nil
    ) {
        self.strokes = strokes
        self.pieceNumber = pieceNumber
        self.canvasWidth = canvasWidth
        self.canvasHeight = canvasHeight
        self.drawingStyle = drawingStyle
        self.styleConfig = styleConfig
        self.format = format
        self.imageURL = imageURL
    }

    /// `canvas_width`/`canvas_height` default to 800/600 if the payload
    /// omits them (protocol-state spec §2.2).
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        strokes = try container.decode([Path].self, forKey: .strokes)
        pieceNumber = try container.decode(Int.self, forKey: .pieceNumber)
        canvasWidth = try container.decodeIfPresent(Int.self, forKey: .canvasWidth) ?? CanvasDefaults.width
        canvasHeight = try container.decodeIfPresent(Int.self, forKey: .canvasHeight) ?? CanvasDefaults.height
        drawingStyle = try container.decodeIfPresent(DrawingStyleType.self, forKey: .drawingStyle)
        styleConfig = try container.decodeIfPresent(DrawingStyleConfig.self, forKey: .styleConfig)
        format = try container.decodeIfPresent(GalleryPieceFormat.self, forKey: .format) ?? .strokes
        imageURL = try container.decodeIfPresent(String.self, forKey: .imageURL)
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

    /// `iteration` is documented "required, defaults 1" (protocol-state spec
    /// §2.2) — same defaults-applied-server-side pattern as the gallery/init
    /// fields above. Decode tolerantly for consistency, even though every
    /// fixture observed so far always includes it.
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decode(ToolExecutionStatus.self, forKey: .status)
        toolName = try container.decodeIfPresent(String.self, forKey: .toolName)
        toolInput = try container.decodeIfPresent(JSONValue.self, forKey: .toolInput)
        stdout = try container.decodeIfPresent(String.self, forKey: .stdout)
        stderr = try container.decodeIfPresent(String.self, forKey: .stderr)
        returnCode = try container.decodeIfPresent(Int.self, forKey: .returnCode)
        iteration = try container.decodeIfPresent(Int.self, forKey: .iteration) ?? 1
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
    /// Broadcast every time `run_painting_program` succeeds (program-painting
    /// spec §1.1) — every successful `paint` tool call, not just "done"
    /// pieces. No `animation_done`-style ack exists for this message; the
    /// agent never waits for the client to finish revealing it. `stages` is
    /// the deduplicated (consecutive-only), in-order list of `cv.stage(...)`
    /// labels used so far in this program run — display-only (spec §4.2);
    /// the reducer keeps it only in the version history for the Studio's
    /// version list. `ops` is the render's total reveal-op count, an
    /// additive server field (`nil` from a server that doesn't send it).
    case paintingVersion(PaintingVersionRef, stages: [String], ops: Int? = nil)
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
        case "painting_version":
            let envelope = try PaintingVersionEnvelope(from: decoder)
            self = .paintingVersion(envelope.ref, stages: envelope.stages, ops: envelope.ops)
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
private struct PaintingVersionEnvelope: Decodable {
    let ref: PaintingVersionRef
    let stages: [String]
    let ops: Int?
    enum CodingKeys: String, CodingKey {
        case pieceNumber = "piece_number"
        case version
        case assetBase = "asset_base"
        case imageWidth = "image_width"
        case imageHeight = "image_height"
        case stages, ops
    }
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ref = PaintingVersionRef(
            pieceNumber: try container.decode(Int.self, forKey: .pieceNumber),
            version: try container.decode(Int.self, forKey: .version),
            assetBase: try container.decode(String.self, forKey: .assetBase),
            imageWidth: try container.decode(Int.self, forKey: .imageWidth),
            imageHeight: try container.decode(Int.self, forKey: .imageHeight)
        )
        stages = try container.decode([String].self, forKey: .stages)
        ops = try container.decodeIfPresent(Int.self, forKey: .ops)
    }
}
