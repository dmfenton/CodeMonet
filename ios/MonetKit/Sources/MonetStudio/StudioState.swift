import MonetProtocol

/// One item in the performance/animation buffer (protocol-state spec §4,
/// "PerformanceItem"). Enqueued by message routing, drained one at a time
/// onto `stage` by `MonetPerformer`.
public enum PerformanceItem: Equatable, Sendable, Identifiable {
    case words(id: String, text: String)
    case event(id: String, message: AgentMessage)
    case strokes(id: String, strokes: [PendingStroke])

    public var id: String {
        switch self {
        case let .words(id, _), let .event(id, _), let .strokes(id, _): id
        }
    }
}

/// The stroke/text/pen playback pipeline's state (protocol-state spec §4
/// `PerformanceState`). Pure value type; advanced only via
/// `MonetStudio.reduce` and `MonetPerformer`'s tick events, never mutated
/// directly by UI code.
public struct PerformanceState: Equatable, Sendable {
    public var buffer: [PerformanceItem] = []
    public var onStage: PerformanceItem?
    public var history: [PerformanceItem] = []
    public var wordIndex: Int = 0
    public var strokeIndex: Int = 0
    public var strokeProgress: Double = 0
    public var revealedText: String = ""
    public var penPosition: Point?
    public var penDown: Bool = false
    public var agentStroke: [Point] = []
    public var agentStrokeStyle: PartialStrokeStyle?
    public var travelTarget: Point?

    public init() {}

    /// Oldest-dropped bound for `history` (protocol-state spec §4, `MAX_HISTORY`).
    public static let maxHistory = 100
}

/// A per-field-optional style override, captured from a stroke's first
/// point/batch (protocol-state spec §5.5 `STROKE_PROGRESS_BATCH`). Mirrors
/// the TS `Partial<StrokeStyle>`.
public struct PartialStrokeStyle: Equatable, Sendable {
    public var color: String?
    public var strokeWidth: Double?
    public var opacity: Double?

    public init(color: String? = nil, strokeWidth: Double? = nil, opacity: Double? = nil) {
        self.color = color
        self.strokeWidth = strokeWidth
        self.opacity = opacity
    }
}

/// A snapshot of the live canvas, taken when entering gallery-view mode, so
/// "back to studio" can restore it exactly (protocol-state spec §5.4).
public struct SavedCanvas: Equatable, Sendable {
    public var strokes: [Path]
    public var canvasWidth: Int
    public var canvasHeight: Int
    public var pieceNumber: Int
    public var drawingStyle: DrawingStyleType
    public var styleConfig: DrawingStyleConfig
    /// Already-settled (program-painting spec §4.1 `LOAD_CANVAS`): an
    /// in-flight reveal interrupted by entering gallery view is snapshotted
    /// via `settlePainting`, so `CLEAR_VIEWING` restores a finished picture,
    /// never a mid-reveal one.
    public var painting: PaintingState

    public init(
        strokes: [Path],
        canvasWidth: Int,
        canvasHeight: Int,
        pieceNumber: Int,
        drawingStyle: DrawingStyleType,
        styleConfig: DrawingStyleConfig,
        painting: PaintingState = PaintingState()
    ) {
        self.strokes = strokes
        self.canvasWidth = canvasWidth
        self.canvasHeight = canvasHeight
        self.pieceNumber = pieceNumber
        self.drawingStyle = drawingStyle
        self.styleConfig = styleConfig
        self.painting = painting
    }
}

/// The full reproducible client state (protocol-state spec §4
/// `CanvasHookState`). A pure value type: every transition is
/// `StudioState.reduce(state, event) -> state`. `StudioStore` (app target)
/// is the only thing that owns a live, mutable instance of this.
public struct StudioState: Equatable, Sendable {
    public var performance = PerformanceState()
    public var strokes: [Path] = []
    public var currentStroke: [Point] = []
    public var thinking: String = ""
    public var messages: [AgentMessage] = []
    public var canvasWidth: Int = CanvasDefaults.width
    public var canvasHeight: Int = CanvasDefaults.height
    public var pieceNumber: Int = 0
    public var viewingPiece: Int?
    /// Set alongside `viewingPiece` when the gallery piece being viewed is
    /// `.raster` (program painting, no vector strokes) — the API-relative
    /// URL of its final image (`LoadCanvasPayload.imageURL`, program-
    /// painting spec §2.1's `galleryRasterImageUrl`). `nil` for a `.strokes`
    /// piece, and whenever `viewingPiece` is `nil`.
    public var viewingImageURL: String?
    public var drawingEnabled: Bool = false
    public var gallery: [GalleryEntry] = []
    /// Client assumes paused until the server says otherwise.
    public var paused: Bool = true
    public var currentIteration: Int = 0
    public var maxIterations: Int = 5
    public var drawingStyle: DrawingStyleType = .plotter
    public var styleConfig: DrawingStyleConfig = .plotter
    public var savedCanvas: SavedCanvas?
    /// Program-painting version/reveal state (program-painting spec §4.1).
    /// `PaintingState()` (both `nil`) means no program painting is active —
    /// the true default for plotter mode and for paint-mode pieces the
    /// agent hasn't called `paint` on yet (legacy stamped/freehand rendering
    /// applies in that case instead, spec §6).
    public var painting = PaintingState()
    /// The live piece's program-painting versions, oldest first: seeded from
    /// `init.painting.versions` when the server sends it, else from
    /// `init.painting` alone, then extended by every accepted
    /// `painting_version` this session. Reset on `clear`/`new_canvas`.
    /// Untouched by gallery viewing — it always describes the live piece.
    public var versions: [PaintingVersionSummary] = []
    /// The live piece's title (`init.title`, or a completed `name_piece`
    /// call's input). `nil` until named.
    public var title: String?
    /// The direction the live piece was started with, when known.
    public var prompt: String?

    public init() {}

    /// The version new agent work is heading toward: one past the latest
    /// known version (1 before any version exists).
    public var workingVersion: Int {
        (versions.map(\.version).max() ?? 0) + 1
    }

    /// `MAX_MESSAGES` bound on `messages` (protocol-state spec §4).
    public static let maxMessages = 50
}
