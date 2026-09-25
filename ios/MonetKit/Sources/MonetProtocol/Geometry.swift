import Foundation

/// A single point in canvas space (800x600 logical units by default, origin
/// top-left, y-down). See ARCHITECTURE.md and the performer-render spec §1.
public struct Point: Codable, Equatable, Sendable, Hashable {
    public var x: Double
    public var y: Double

    public init(x: Double, y: Double) {
        self.x = x
        self.y = y
    }
}

/// How `Path.points` should be interpreted. `.svg` paths carry no points;
/// geometry lives entirely in `Path.d`. See performer-render spec §2.2.
public enum PathType: String, Codable, Equatable, Sendable {
    case line
    case quadratic
    case cubic
    case polyline
    case svg
}

/// Who authored a stroke. Drives which half of `DrawingStyleConfig` supplies
/// the default style when a path omits explicit style fields.
public enum PathAuthor: String, Codable, Equatable, Sendable {
    case agent
    case human
}

/// One stroke or shape, as sent over the wire or stored in `StudioState`.
///
/// Every field except `type`/`points` is independently optional on the wire
/// (the server's `model_dump` excludes `None` fields) — absent means "use the
/// effective `DrawingStyleConfig` default for this path's author", never an
/// explicit zero/null. See performer-render spec §2.3 and
/// `getEffectiveStyle` in protocol-state spec §2.5 for the exact fallback
/// rules a renderer must apply.
public struct Path: Codable, Equatable, Sendable {
    public var type: PathType
    public var points: [Point]
    /// SVG path `d` string. Only present when `type == .svg`.
    public var d: String?
    public var author: PathAuthor?
    /// Hex color, e.g. "#e94560".
    public var color: String?
    public var strokeWidth: Double?
    /// 0...1.
    public var opacity: Double?
    /// Hex fill color for closed shapes.
    public var fill: String?
    /// 0...1.
    public var fillOpacity: Double?
    /// Paint-mode brush preset name. Never applied in plotter mode.
    public var brush: BrushName?

    public init(
        type: PathType,
        points: [Point] = [],
        d: String? = nil,
        author: PathAuthor? = nil,
        color: String? = nil,
        strokeWidth: Double? = nil,
        opacity: Double? = nil,
        fill: String? = nil,
        fillOpacity: Double? = nil,
        brush: BrushName? = nil
    ) {
        self.type = type
        self.points = points
        self.d = d
        self.author = author
        self.color = color
        self.strokeWidth = strokeWidth
        self.opacity = opacity
        self.fill = fill
        self.fillOpacity = fillOpacity
        self.brush = brush
    }

    enum CodingKeys: String, CodingKey {
        case type, points, d, author, color
        case strokeWidth = "stroke_width"
        case opacity
        case fill
        case fillOpacity = "fill_opacity"
        case brush
    }
}

/// Logical canvas size for a new piece, before any server override.
public enum CanvasDefaults {
    public static let width = 800
    public static let height = 600
}
