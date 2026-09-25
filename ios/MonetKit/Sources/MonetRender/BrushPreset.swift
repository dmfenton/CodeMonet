import MonetProtocol

/// Freehand/bristle tuning per brush (performer-render spec §6). Used for
/// bristle sub-stroke geometry and the perfect-freehand taper/smoothing
/// options — a different table from `StampDynamics` (§7.2), tuned
/// independently for a different renderer.
public struct BrushPreset: Equatable, Sendable {
    public var bristleCount: Int
    public var bristleSpread: Double
    public var bristleOpacity: Double
    public var bristleWidthRatio: Double
    public var mainOpacity: Double
    public var baseWidth: Double
    public var taper: Double
    public var pressureResponse: Double
    public var edgeNoise: Double
    public var wetEdges: Double
    public var smoothing: Double

    public init(
        bristleCount: Int, bristleSpread: Double, bristleOpacity: Double, bristleWidthRatio: Double,
        mainOpacity: Double, baseWidth: Double, taper: Double, pressureResponse: Double,
        edgeNoise: Double, wetEdges: Double, smoothing: Double
    ) {
        self.bristleCount = bristleCount
        self.bristleSpread = bristleSpread
        self.bristleOpacity = bristleOpacity
        self.bristleWidthRatio = bristleWidthRatio
        self.mainOpacity = mainOpacity
        self.baseWidth = baseWidth
        self.taper = taper
        self.pressureResponse = pressureResponse
        self.edgeNoise = edgeNoise
        self.wetEdges = wetEdges
        self.smoothing = smoothing
    }

    /// Exact table, performer-render spec §6. `DEFAULT_BRUSH` is `.oilRound`.
    public static let table: [BrushName: BrushPreset] = [
        .oilRound: BrushPreset(bristleCount: 3, bristleSpread: 0.7, bristleOpacity: 0.14, bristleWidthRatio: 0.35, mainOpacity: 0.75, baseWidth: 10, taper: 0.7, pressureResponse: 0.5, edgeNoise: 0, wetEdges: 0, smoothing: 0.6),
        .oilFlat: BrushPreset(bristleCount: 4, bristleSpread: 0.5, bristleOpacity: 0.13, bristleWidthRatio: 0.25, mainOpacity: 0.8, baseWidth: 12, taper: 0.3, pressureResponse: 0.3, edgeNoise: 0, wetEdges: 0, smoothing: 0.4),
        .oilFilbert: BrushPreset(bristleCount: 3, bristleSpread: 0.6, bristleOpacity: 0.14, bristleWidthRatio: 0.3, mainOpacity: 0.78, baseWidth: 10, taper: 0.6, pressureResponse: 0.4, edgeNoise: 0, wetEdges: 0, smoothing: 0.7),
        .watercolor: BrushPreset(bristleCount: 0, bristleSpread: 0, bristleOpacity: 0, bristleWidthRatio: 0, mainOpacity: 0.35, baseWidth: 14, taper: 0.5, pressureResponse: 0.6, edgeNoise: 0.15, wetEdges: 0.4, smoothing: 0.8),
        .dryBrush: BrushPreset(bristleCount: 7, bristleSpread: 1.0, bristleOpacity: 0.22, bristleWidthRatio: 0.2, mainOpacity: 0.3, baseWidth: 10, taper: 0.4, pressureResponse: 0.7, edgeNoise: 0, wetEdges: 0, smoothing: 0.3),
        .paletteKnife: BrushPreset(bristleCount: 0, bristleSpread: 0, bristleOpacity: 0, bristleWidthRatio: 0, mainOpacity: 0.95, baseWidth: 16, taper: 0.1, pressureResponse: 0.8, edgeNoise: 0.05, wetEdges: 0, smoothing: 0.2),
        .ink: BrushPreset(bristleCount: 0, bristleSpread: 0, bristleOpacity: 0, bristleWidthRatio: 0, mainOpacity: 0.9, baseWidth: 6, taper: 0.9, pressureResponse: 0.9, edgeNoise: 0, wetEdges: 0, smoothing: 0.7),
        .pencil: BrushPreset(bristleCount: 0, bristleSpread: 0, bristleOpacity: 0, bristleWidthRatio: 0, mainOpacity: 0.85, baseWidth: 2, taper: 0.2, pressureResponse: 0.4, edgeNoise: 0, wetEdges: 0, smoothing: 0.3),
        .charcoal: BrushPreset(bristleCount: 3, bristleSpread: 0.4, bristleOpacity: 0.3, bristleWidthRatio: 0.5, mainOpacity: 0.6, baseWidth: 5, taper: 0.4, pressureResponse: 0.5, edgeNoise: 0.1, wetEdges: 0, smoothing: 0.5),
        .marker: BrushPreset(bristleCount: 0, bristleSpread: 0, bristleOpacity: 0, bristleWidthRatio: 0, mainOpacity: 0.75, baseWidth: 8, taper: 0.15, pressureResponse: 0.1, edgeNoise: 0, wetEdges: 0.2, smoothing: 0.4),
        .airbrush: BrushPreset(bristleCount: 0, bristleSpread: 0, bristleOpacity: 0, bristleWidthRatio: 0, mainOpacity: 0.25, baseWidth: 20, taper: 0.0, pressureResponse: 0.3, edgeNoise: 0, wetEdges: 0, smoothing: 0.9),
        .splatter: BrushPreset(bristleCount: 20, bristleSpread: 2.0, bristleOpacity: 0.6, bristleWidthRatio: 0.15, mainOpacity: 0.5, baseWidth: 8, taper: 0.3, pressureResponse: 0.2, edgeNoise: 0.3, wetEdges: 0, smoothing: 0.5),
    ]

    public static let defaultBrush: BrushName = .oilRound

    public static func preset(for brush: BrushName?) -> BrushPreset {
        table[brush ?? defaultBrush] ?? table[defaultBrush]!
    }
}
