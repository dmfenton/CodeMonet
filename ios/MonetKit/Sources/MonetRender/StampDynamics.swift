import MonetProtocol

/// Per-brush tuning for the stamp model (performer-render spec §7.2). This
/// is a *different* table from `BrushPreset` (freehand/bristle tuning,
/// §6) — the two were tuned independently for different renderers and must
/// not be conflated, even though they're keyed by the same `BrushName`.
public struct StampDynamics: Equatable, Sendable {
    public var spacing: Double
    public var aspect: Double
    public var streaks: Int
    public var streakContrast: Double
    public var edgeRough: Double
    public var dryness: Double
    public var loadFade: Double
    public var hueJitter: Double
    public var satJitter: Double
    public var valJitter: Double
    public var taper: Double
    public var widthWobble: Double
    public var soften: Double
    public var wetEdge: Double

    public init(
        spacing: Double, aspect: Double, streaks: Int, streakContrast: Double,
        edgeRough: Double, dryness: Double, loadFade: Double, hueJitter: Double,
        satJitter: Double, valJitter: Double, taper: Double, widthWobble: Double,
        soften: Double, wetEdge: Double
    ) {
        self.spacing = spacing
        self.aspect = aspect
        self.streaks = streaks
        self.streakContrast = streakContrast
        self.edgeRough = edgeRough
        self.dryness = dryness
        self.loadFade = loadFade
        self.hueJitter = hueJitter
        self.satJitter = satJitter
        self.valJitter = valJitter
        self.taper = taper
        self.widthWobble = widthWobble
        self.soften = soften
        self.wetEdge = wetEdge
    }

    /// Fallback for `nil`/unrecognized brush (performer-render spec §7.2).
    public static let `default` = StampDynamics(
        spacing: 0.35, aspect: 1.7, streaks: 5, streakContrast: 0.45, edgeRough: 0.35,
        dryness: 0.12, loadFade: 0.25, hueJitter: 0.012, satJitter: 0.10, valJitter: 0.08,
        taper: 0.6, widthWobble: 0.15, soften: 0, wetEdge: 0
    )

    /// Exact per-brush table, performer-render spec §7.2.
    public static let table: [BrushName: StampDynamics] = [
        .oilRound: StampDynamics(spacing: 0.32, aspect: 1.5, streaks: 6, streakContrast: 0.42, edgeRough: 0.3, dryness: 0.10, loadFade: 0.25, hueJitter: 0.012, satJitter: 0.10, valJitter: 0.08, taper: 0.65, widthWobble: 0.15, soften: 0, wetEdge: 0),
        .oilFlat: StampDynamics(spacing: 0.30, aspect: 1.25, streaks: 8, streakContrast: 0.75, edgeRough: 0.22, dryness: 0.14, loadFade: 0.25, hueJitter: 0.010, satJitter: 0.10, valJitter: 0.08, taper: 0.3, widthWobble: 0.15, soften: 0, wetEdge: 0),
        .oilFilbert: StampDynamics(spacing: 0.34, aspect: 1.8, streaks: 6, streakContrast: 0.5, edgeRough: 0.35, dryness: 0.12, loadFade: 0.25, hueJitter: 0.014, satJitter: 0.10, valJitter: 0.08, taper: 0.55, widthWobble: 0.15, soften: 0, wetEdge: 0),
        .dryBrush: StampDynamics(spacing: 0.30, aspect: 1.9, streaks: 9, streakContrast: 0.95, edgeRough: 0.6, dryness: 0.55, loadFade: 0.5, hueJitter: 0.010, satJitter: 0.10, valJitter: 0.08, taper: 0.5, widthWobble: 0.3, soften: 0, wetEdge: 0),
        .paletteKnife: StampDynamics(spacing: 0.42, aspect: 2.6, streaks: 3, streakContrast: 0.35, edgeRough: 0.5, dryness: 0.20, loadFade: 0.45, hueJitter: 0.008, satJitter: 0.06, valJitter: 0.12, taper: 0.15, widthWobble: 0.1, soften: 0, wetEdge: 0),
        .watercolor: StampDynamics(spacing: 0.40, aspect: 1.6, streaks: 0, streakContrast: 0, edgeRough: 0.45, dryness: 0.05, loadFade: 0.15, hueJitter: 0.010, satJitter: 0.12, valJitter: 0.05, taper: 0.5, widthWobble: 0.28, soften: 0.6, wetEdge: 0.55),
        .airbrush: StampDynamics(spacing: 0.45, aspect: 1.0, streaks: 0, streakContrast: 0, edgeRough: 0, dryness: 0, loadFade: 0, hueJitter: 0.004, satJitter: 0.04, valJitter: 0.03, taper: 0, widthWobble: 0.05, soften: 1.0, wetEdge: 0),
        .charcoal: StampDynamics(spacing: 0.32, aspect: 1.4, streaks: 5, streakContrast: 0.55, edgeRough: 0.5, dryness: 0.45, loadFade: 0.3, hueJitter: 0, satJitter: 0.04, valJitter: 0.10, taper: 0.4, widthWobble: 0.25, soften: 0, wetEdge: 0),
        .ink: StampDynamics(spacing: 0.28, aspect: 1.4, streaks: 0, streakContrast: 0, edgeRough: 0.15, dryness: 0.06, loadFade: 0.2, hueJitter: 0, satJitter: 0.02, valJitter: 0.04, taper: 0.9, widthWobble: 0.18, soften: 0, wetEdge: 0),
        .pencil: StampDynamics(spacing: 0.30, aspect: 1.2, streaks: 2, streakContrast: 0.4, edgeRough: 0.3, dryness: 0.35, loadFade: 0.1, hueJitter: 0, satJitter: 0.02, valJitter: 0.06, taper: 0.25, widthWobble: 0.12, soften: 0, wetEdge: 0),
        .marker: StampDynamics(spacing: 0.30, aspect: 1.3, streaks: 0, streakContrast: 0, edgeRough: 0.12, dryness: 0.04, loadFade: 0.08, hueJitter: 0.004, satJitter: 0.03, valJitter: 0.03, taper: 0.15, widthWobble: 0.06, soften: 0.25, wetEdge: 0),
        .splatter: StampDynamics(spacing: 1.6, aspect: 0.9, streaks: 0, streakContrast: 0, edgeRough: 0.7, dryness: 0.3, loadFade: 0.2, hueJitter: 0.02, satJitter: 0.12, valJitter: 0.12, taper: 0.2, widthWobble: 0.8, soften: 0, wetEdge: 0),
    ]

    public static func dynamics(for brush: BrushName?) -> StampDynamics {
        guard let brush else { return .default }
        return table[brush] ?? .default
    }
}
