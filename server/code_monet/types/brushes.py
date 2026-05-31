"""Brush preset definitions for paint mode."""

from pydantic import BaseModel


class BrushPreset(BaseModel):
    """Brush preset defining how strokes are rendered.

    The server expands a single stroke into multiple sub-strokes
    based on these parameters to create paint-like effects.
    """

    name: str  # Unique identifier (e.g., "oil_round")
    display_name: str  # Human-readable name
    description: str  # For agent prompt

    # Bristle rendering (sub-strokes)
    bristle_count: int = 0  # Number of parallel sub-strokes (0 = solid stroke)
    bristle_spread: float = 0.8  # Distance between bristles (× stroke width)
    bristle_opacity: float = 0.3  # Opacity of each bristle stroke
    bristle_width_ratio: float = 0.3  # Width of bristle (× main width)

    # Main stroke
    main_opacity: float = 0.8  # Opacity of the main/base stroke
    base_width: float = 8.0  # Default stroke width

    # Stroke shape
    taper: float = 0.7  # How much ends taper (0 = none, 1 = full point)
    pressure_response: float = 0.5  # How velocity affects width (0 = none, 1 = full)

    # Edge effects
    edge_noise: float = 0.0  # Random edge displacement (0-1)
    wet_edges: float = 0.0  # Opacity boost at stroke ends (0-1)

    # Smoothing
    smoothing: float = 0.5  # Catmull-Rom tension (0 = sharp, 1 = very smooth)


# ============================================================================
# BRUSH PRESETS
# ============================================================================

BRUSH_OIL_ROUND = BrushPreset(
    name="oil_round",
    display_name="Oil Round",
    description="Classic round oil brush. Soft edges, visible bristle texture. Good for blending and details.",
    bristle_count=3,
    bristle_spread=0.7,
    bristle_opacity=0.14,
    bristle_width_ratio=0.35,
    main_opacity=0.75,
    base_width=10.0,
    taper=0.7,
    pressure_response=0.5,
    smoothing=0.6,
)

BRUSH_OIL_FLAT = BrushPreset(
    name="oil_flat",
    display_name="Oil Flat",
    description="Flat oil brush. Parallel bristle marks, sharp edges. Good for blocking in shapes and bold strokes.",
    bristle_count=4,
    bristle_spread=0.5,
    bristle_opacity=0.13,
    bristle_width_ratio=0.25,
    main_opacity=0.8,
    base_width=12.0,
    taper=0.3,
    pressure_response=0.3,
    smoothing=0.4,
)

BRUSH_OIL_FILBERT = BrushPreset(
    name="oil_filbert",
    display_name="Oil Filbert",
    description="Rounded flat brush. Organic flowing strokes. Good for foliage, clouds, organic shapes.",
    bristle_count=3,
    bristle_spread=0.6,
    bristle_opacity=0.14,
    bristle_width_ratio=0.3,
    main_opacity=0.78,
    base_width=10.0,
    taper=0.6,
    pressure_response=0.4,
    smoothing=0.7,
)

BRUSH_WATERCOLOR = BrushPreset(
    name="watercolor",
    display_name="Watercolor",
    description="Wet watercolor brush. Very translucent with soft edges. Colors pool at stroke ends.",
    bristle_count=0,
    main_opacity=0.35,
    base_width=14.0,
    taper=0.5,
    pressure_response=0.6,
    edge_noise=0.15,
    wet_edges=0.4,
    smoothing=0.8,
)

BRUSH_DRY_BRUSH = BrushPreset(
    name="dry_brush",
    display_name="Dry Brush",
    description="Dry brush technique. Scratchy, broken strokes with visible gaps. Good for texture and grass.",
    bristle_count=7,
    bristle_spread=1.0,
    bristle_opacity=0.22,
    bristle_width_ratio=0.2,
    main_opacity=0.3,
    base_width=10.0,
    taper=0.4,
    pressure_response=0.7,
    smoothing=0.3,
)

BRUSH_PALETTE_KNIFE = BrushPreset(
    name="palette_knife",
    display_name="Palette Knife",
    description="Thick paint application. Sharp edges, heavy texture. Good for impasto effects and bold marks.",
    bristle_count=0,
    main_opacity=0.95,
    base_width=16.0,
    taper=0.1,
    pressure_response=0.8,
    edge_noise=0.05,
    smoothing=0.2,
)

BRUSH_INK = BrushPreset(
    name="ink",
    display_name="Ink Brush",
    description="Asian-style ink brush. Highly pressure-sensitive with elegant taper. Good for calligraphy and expressive lines.",
    bristle_count=0,
    main_opacity=0.9,
    base_width=6.0,
    taper=0.9,
    pressure_response=0.9,
    smoothing=0.7,
)

BRUSH_PENCIL = BrushPreset(
    name="pencil",
    display_name="Pencil",
    description="Graphite pencil. Thin, consistent lines. Good for sketching and outlines.",
    bristle_count=0,
    main_opacity=0.85,
    base_width=2.0,
    taper=0.2,
    pressure_response=0.4,
    smoothing=0.3,
)

BRUSH_CHARCOAL = BrushPreset(
    name="charcoal",
    display_name="Charcoal",
    description="Soft charcoal. Smudgy edges with slight texture. Good for loose sketching and value studies.",
    bristle_count=3,
    bristle_spread=0.4,
    bristle_opacity=0.3,
    bristle_width_ratio=0.5,
    main_opacity=0.6,
    base_width=5.0,
    taper=0.4,
    pressure_response=0.5,
    edge_noise=0.1,
    smoothing=0.5,
)

BRUSH_MARKER = BrushPreset(
    name="marker",
    display_name="Marker",
    description="Flat marker. Solid color with slight edge bleed. Good for fills and graphic illustration.",
    bristle_count=0,
    main_opacity=0.75,
    base_width=8.0,
    taper=0.15,
    pressure_response=0.1,
    wet_edges=0.2,
    smoothing=0.4,
)

BRUSH_AIRBRUSH = BrushPreset(
    name="airbrush",
    display_name="Airbrush",
    description="Soft airbrush. Very smooth gradients with no hard edges. Good for shading and backgrounds.",
    bristle_count=0,
    main_opacity=0.25,
    base_width=20.0,
    taper=0.0,
    pressure_response=0.3,
    smoothing=0.9,
)

BRUSH_SPLATTER = BrushPreset(
    name="splatter",
    display_name="Splatter",
    description="Paint splatter effect. Random dots around the stroke path. Good for texture and effects.",
    bristle_count=20,
    bristle_spread=2.0,
    bristle_opacity=0.6,
    bristle_width_ratio=0.15,
    main_opacity=0.5,
    base_width=8.0,
    taper=0.3,
    pressure_response=0.2,
    edge_noise=0.3,
    smoothing=0.5,
)

# Registry of all brush presets
BRUSH_PRESETS: dict[str, BrushPreset] = {
    "oil_round": BRUSH_OIL_ROUND,
    "oil_flat": BRUSH_OIL_FLAT,
    "oil_filbert": BRUSH_OIL_FILBERT,
    "watercolor": BRUSH_WATERCOLOR,
    "dry_brush": BRUSH_DRY_BRUSH,
    "palette_knife": BRUSH_PALETTE_KNIFE,
    "ink": BRUSH_INK,
    "pencil": BRUSH_PENCIL,
    "charcoal": BRUSH_CHARCOAL,
    "marker": BRUSH_MARKER,
    "airbrush": BRUSH_AIRBRUSH,
    "splatter": BRUSH_SPLATTER,
}

# Default brush for paint mode
DEFAULT_BRUSH = "oil_round"


def get_brush_preset(name: str) -> BrushPreset | None:
    """Get a brush preset by name."""
    return BRUSH_PRESETS.get(name)
