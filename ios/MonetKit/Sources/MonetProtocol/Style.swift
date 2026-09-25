import Foundation

/// The 12 paint-mode brush presets. Selects both the freehand/bristle table
/// (performer-render spec §6) and the independent stamp-dynamics table (§7.2)
/// — the two are tuned separately and must not be conflated. Never applied
/// for completed strokes in plotter mode.
public enum BrushName: String, Codable, Equatable, Sendable, CaseIterable {
    case oilRound = "oil_round"
    case oilFlat = "oil_flat"
    case oilFilbert = "oil_filbert"
    case watercolor
    case dryBrush = "dry_brush"
    case paletteKnife = "palette_knife"
    case ink
    case pencil
    case charcoal
    case marker
    case airbrush
    case splatter
}

public enum StrokeLinecap: String, Codable, Equatable, Sendable {
    case round, butt, square
}

public enum StrokeLinejoin: String, Codable, Equatable, Sendable {
    case round, miter, bevel
}

/// The resolved style for one "half" (agent or human) of a `DrawingStyleConfig`.
public struct StrokeStyle: Codable, Equatable, Sendable {
    public var color: String
    public var strokeWidth: Double
    public var opacity: Double
    public var strokeLinecap: StrokeLinecap
    public var strokeLinejoin: StrokeLinejoin

    public init(
        color: String,
        strokeWidth: Double,
        opacity: Double,
        strokeLinecap: StrokeLinecap,
        strokeLinejoin: StrokeLinejoin
    ) {
        self.color = color
        self.strokeWidth = strokeWidth
        self.opacity = opacity
        self.strokeLinecap = strokeLinecap
        self.strokeLinejoin = strokeLinejoin
    }

    enum CodingKeys: String, CodingKey {
        case color
        case strokeWidth = "stroke_width"
        case opacity
        case strokeLinecap = "stroke_linecap"
        case strokeLinejoin = "stroke_linejoin"
    }
}

/// Which drawing mode a canvas is in. Sent by the server on `init`/
/// `load_canvas`/`new_canvas` and chosen client-side for the *next* canvas
/// via the style picker (protocol-state spec §2.3, ux spec §5.1).
public enum DrawingStyleType: String, Codable, Equatable, Sendable {
    case plotter
    case paint
}

/// Full style configuration for a canvas, as the server always sends it on
/// `init`/`load_canvas`. The client decodes whatever arrives rather than
/// hardcoding these — `.plotter`/`.paint` below exist only as the fallback
/// used by the pre-session style picker, before any canvas/session exists to
/// source a config from. Values must match byte-for-byte (protocol-state
/// spec §2.3).
public struct DrawingStyleConfig: Codable, Equatable, Sendable {
    public var type: DrawingStyleType
    public var name: String
    public var description: String
    public var agentStroke: StrokeStyle
    public var humanStroke: StrokeStyle
    public var supportsColor: Bool
    public var supportsVariableWidth: Bool
    public var supportsOpacity: Bool
    public var colorPalette: [String]?

    public init(
        type: DrawingStyleType,
        name: String,
        description: String,
        agentStroke: StrokeStyle,
        humanStroke: StrokeStyle,
        supportsColor: Bool,
        supportsVariableWidth: Bool,
        supportsOpacity: Bool,
        colorPalette: [String]?
    ) {
        self.type = type
        self.name = name
        self.description = description
        self.agentStroke = agentStroke
        self.humanStroke = humanStroke
        self.supportsColor = supportsColor
        self.supportsVariableWidth = supportsVariableWidth
        self.supportsOpacity = supportsOpacity
        self.colorPalette = colorPalette
    }

    enum CodingKeys: String, CodingKey {
        case type, name, description
        case agentStroke = "agent_stroke"
        case humanStroke = "human_stroke"
        case supportsColor = "supports_color"
        case supportsVariableWidth = "supports_variable_width"
        case supportsOpacity = "supports_opacity"
        case colorPalette = "color_palette"
    }

    /// Exact plotter constant (protocol-state spec §2.3). Monochrome, fixed
    /// 2.5px strokes, no per-path overrides honored.
    public static let plotter = DrawingStyleConfig(
        type: .plotter,
        name: "Plotter",
        description: "Monochrome pen-plotter style",
        agentStroke: StrokeStyle(color: "#1a1a2e", strokeWidth: 2.5, opacity: 1.0, strokeLinecap: .round, strokeLinejoin: .round),
        humanStroke: StrokeStyle(color: "#0066CC", strokeWidth: 2.5, opacity: 1.0, strokeLinecap: .round, strokeLinejoin: .round),
        supportsColor: false,
        supportsVariableWidth: false,
        supportsOpacity: false,
        colorPalette: nil
    )

    /// Exact paint constant (protocol-state spec §2.3). Colored 8px strokes,
    /// 85% opacity default, 11-swatch palette, per-path overrides honored.
    public static let paint = DrawingStyleConfig(
        type: .paint,
        name: "Paint",
        description: "Colored painterly style",
        agentStroke: StrokeStyle(color: "#1a1a2e", strokeWidth: 8.0, opacity: 0.85, strokeLinecap: .round, strokeLinejoin: .round),
        humanStroke: StrokeStyle(color: "#e94560", strokeWidth: 8.0, opacity: 0.85, strokeLinecap: .round, strokeLinejoin: .round),
        supportsColor: true,
        supportsVariableWidth: true,
        supportsOpacity: true,
        colorPalette: [
            "#1a1a2e", "#e94560", "#7b68ee", "#4ecdc4", "#ffd93d", "#ff6b6b",
            "#4ade80", "#3b82f6", "#f97316", "#a855f7", "#ffffff",
        ]
    )

    /// `getEffectiveStyle` (protocol-state spec §2.5): resolves the style a
    /// renderer should actually use for `path`, given this config. Plotter
    /// mode ignores every per-path override; paint mode falls back field by
    /// field, gated by the corresponding `supports*` flag.
    public func effectiveStyle(for path: Path) -> StrokeStyle {
        let base = path.author == .human ? humanStroke : agentStroke
        guard type == .paint else { return base }
        var resolved = base
        if supportsColor, let color = path.color { resolved.color = color }
        if supportsVariableWidth, let width = path.strokeWidth { resolved.strokeWidth = width }
        if supportsOpacity, let opacity = path.opacity { resolved.opacity = opacity }
        return resolved
    }
}
