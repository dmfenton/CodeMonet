import Foundation

/// One saved piece, as listed in `init.gallery` / `GET /gallery` /
/// `gallery_update`. See protocol-state spec §2.2.
public struct GalleryEntry: Codable, Equatable, Sendable, Identifiable {
    public var id: String
    public var createdAt: String
    public var pieceNumber: Int
    public var strokeCount: Int
    public var width: Int
    public var height: Int
    public var drawingStyle: DrawingStyleType
    public var title: String?
    public var thumbnailToken: String?
    /// `"strokes"` (vector) or `"raster"` (program painting). Server default
    /// is `"strokes"` (program-painting spec §5, `GalleryEntry.format`).
    public var format: GalleryPieceFormat

    public init(
        id: String,
        createdAt: String,
        pieceNumber: Int,
        strokeCount: Int,
        width: Int,
        height: Int,
        drawingStyle: DrawingStyleType,
        title: String?,
        thumbnailToken: String?,
        format: GalleryPieceFormat = .strokes
    ) {
        self.id = id
        self.createdAt = createdAt
        self.pieceNumber = pieceNumber
        self.strokeCount = strokeCount
        self.width = width
        self.height = height
        self.drawingStyle = drawingStyle
        self.title = title
        self.thumbnailToken = thumbnailToken
        self.format = format
    }

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case pieceNumber = "piece_number"
        case strokeCount = "stroke_count"
        case width, height
        case drawingStyle = "drawing_style"
        case title
        case thumbnailToken = "thumbnail_token"
        case format
    }

    /// Custom decode: `width`/`height`/`drawing_style` are documented as
    /// "required, defaults ..." server-side (Pydantic field defaults), which
    /// in practice means a recording made before the field existed omits the
    /// key entirely. Confirmed concretely in `text_chunking_flow.json`'s
    /// `init.gallery[]`/`gallery_update.canvases[]` entries, which carry
    /// neither `width` nor `height` (protocol-state spec §2.2, §10). Decode
    /// tolerantly and fall back to the same defaults the current server
    /// schema declares, rather than throwing on an older fixture.
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        createdAt = try container.decode(String.self, forKey: .createdAt)
        pieceNumber = try container.decode(Int.self, forKey: .pieceNumber)
        strokeCount = try container.decode(Int.self, forKey: .strokeCount)
        width = try container.decodeIfPresent(Int.self, forKey: .width) ?? CanvasDefaults.width
        height = try container.decodeIfPresent(Int.self, forKey: .height) ?? CanvasDefaults.height
        drawingStyle = try container.decodeIfPresent(DrawingStyleType.self, forKey: .drawingStyle) ?? .plotter
        title = try container.decodeIfPresent(String.self, forKey: .title)
        thumbnailToken = try container.decodeIfPresent(String.self, forKey: .thumbnailToken)
        format = try container.decodeIfPresent(GalleryPieceFormat.self, forKey: .format) ?? .strokes
    }
}

/// Whether a gallery piece's detail view is vector strokes the client
/// renders itself, or a server-rasterized program-painting image
/// (program-painting spec §5). Always present on current server responses;
/// modeled as an unknown-tolerant enum (defaulting to `.strokes`, matching
/// the server's own field default) rather than a plain `String` so callers
/// get exhaustive-switch safety without a decode failure on a future value.
public enum GalleryPieceFormat: Equatable, Sendable {
    case strokes
    case raster
    case other(String)
}

extension GalleryPieceFormat: Codable {
    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        switch raw {
        case "strokes": self = .strokes
        case "raster": self = .raster
        default: self = .other(raw)
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .strokes: try container.encode("strokes")
        case .raster: try container.encode("raster")
        case let .other(raw): try container.encode(raw)
        }
    }
}

/// A committed stroke queued for animated playback, fetched from
/// `GET /strokes/pending` after an `agent_strokes_ready` message. `points` is
/// the server's pre-interpolated point list (playback timing only, see
/// performer-render spec §10) — distinct from `path.points` (final geometry).
public struct PendingStroke: Codable, Equatable, Sendable {
    public var batchId: Int
    public var path: Path
    public var points: [Point]

    public init(batchId: Int, path: Path, points: [Point]) {
        self.batchId = batchId
        self.path = path
        self.points = points
    }

    enum CodingKeys: String, CodingKey {
        case batchId = "batch_id"
        case path, points
    }
}

/// `GET /strokes/pending` response body.
public struct PendingStrokesResponse: Codable, Equatable, Sendable {
    public var strokes: [PendingStroke]
    public var count: Int
    public var pieceNumber: Int

    public init(strokes: [PendingStroke], count: Int, pieceNumber: Int) {
        self.strokes = strokes
        self.count = count
        self.pieceNumber = pieceNumber
    }

    enum CodingKeys: String, CodingKey {
        case strokes, count
        case pieceNumber = "piece_number"
    }
}

/// `GET /gallery/{piece_number}/strokes` response body — a read-only
/// snapshot of a saved piece, shaped like `load_canvas` minus the wrapper.
public struct GalleryPieceStrokes: Codable, Equatable, Sendable {
    public var strokes: [Path]
    public var pieceNumber: Int
    public var canvasWidth: Int
    public var canvasHeight: Int
    public var drawingStyle: DrawingStyleType
    public var styleConfig: DrawingStyleConfig?
    /// Always present on current server responses; older recordings may
    /// omit it, treated as `.strokes` for forward compat (program-painting
    /// spec §2.2).
    public var format: GalleryPieceFormat
    /// Absolute-path URL of `final.png` (relative to the API origin),
    /// present iff `format == .raster`. `strokes` may be non-empty even for
    /// a raster piece (human vector strokes drawn on top) — both must be
    /// rendered together, raster as the base layer.
    public var imageURL: String?
    /// Additive server fields (piece-history change): all optional so an
    /// older server's response decodes with them `nil`/empty, and the detail
    /// view then shows only the final image.
    public var title: String?
    public var prompt: String?
    public var strokeCount: Int?
    /// Every saved version of the piece, oldest first. Empty when absent.
    public var versions: [PaintingVersionSummary]

    public init(
        strokes: [Path],
        pieceNumber: Int,
        canvasWidth: Int,
        canvasHeight: Int,
        drawingStyle: DrawingStyleType,
        styleConfig: DrawingStyleConfig?,
        format: GalleryPieceFormat = .strokes,
        imageURL: String? = nil,
        title: String? = nil,
        prompt: String? = nil,
        strokeCount: Int? = nil,
        versions: [PaintingVersionSummary] = []
    ) {
        self.strokes = strokes
        self.pieceNumber = pieceNumber
        self.canvasWidth = canvasWidth
        self.canvasHeight = canvasHeight
        self.drawingStyle = drawingStyle
        self.styleConfig = styleConfig
        self.format = format
        self.imageURL = imageURL
        self.title = title
        self.prompt = prompt
        self.strokeCount = strokeCount
        self.versions = versions
    }

    enum CodingKeys: String, CodingKey {
        case strokes
        case pieceNumber = "piece_number"
        case canvasWidth = "canvas_width"
        case canvasHeight = "canvas_height"
        case drawingStyle = "drawing_style"
        case styleConfig = "style_config"
        case format
        case imageURL = "image_url"
        case title, prompt
        case strokeCount = "stroke_count"
        case versions
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        strokes = try container.decode([Path].self, forKey: .strokes)
        pieceNumber = try container.decode(Int.self, forKey: .pieceNumber)
        canvasWidth = try container.decode(Int.self, forKey: .canvasWidth)
        canvasHeight = try container.decode(Int.self, forKey: .canvasHeight)
        drawingStyle = try container.decode(DrawingStyleType.self, forKey: .drawingStyle)
        styleConfig = try container.decodeIfPresent(DrawingStyleConfig.self, forKey: .styleConfig)
        format = try container.decodeIfPresent(GalleryPieceFormat.self, forKey: .format) ?? .strokes
        imageURL = try container.decodeIfPresent(String.self, forKey: .imageURL)
        title = try container.decodeIfPresent(String.self, forKey: .title)
        prompt = try container.decodeIfPresent(String.self, forKey: .prompt)
        strokeCount = try container.decodeIfPresent(Int.self, forKey: .strokeCount)
        // Element-wise: one malformed version must not fail the whole detail.
        versions = (try? container.decodeIfPresent(LossyArray<PaintingVersionSummary>.self, forKey: .versions))?
            .elements ?? []
    }
}
