/**
 * Shared type definitions for the Drawing Agent.
 * Platform-agnostic - used by both React Native and web.
 */

// Path types
export interface Point {
  x: number;
  y: number;
}

export type PathType = 'line' | 'quadratic' | 'cubic' | 'polyline' | 'svg';

// Drawing style types
export type DrawingStyleType = 'plotter' | 'paint';

export interface StrokeStyle {
  color: string; // Hex color
  stroke_width: number; // Stroke width in canvas units
  opacity: number; // 0-1 alpha value
  stroke_linecap: 'round' | 'butt' | 'square';
  stroke_linejoin: 'round' | 'miter' | 'bevel';
}

export interface DrawingStyleConfig {
  type: DrawingStyleType;
  name: string;
  description: string;
  agent_stroke: StrokeStyle;
  human_stroke: StrokeStyle;
  supports_color: boolean;
  supports_variable_width: boolean;
  supports_opacity: boolean;
  color_palette: string[] | null;
}

// Pre-defined style configurations (mirrors backend)
export const PLOTTER_STYLE: DrawingStyleConfig = {
  type: 'plotter',
  name: 'Plotter',
  description: 'Monochrome pen plotter style with crisp black lines',
  agent_stroke: {
    color: '#1a1a2e',
    stroke_width: 2.5,
    opacity: 1.0,
    stroke_linecap: 'round',
    stroke_linejoin: 'round',
  },
  human_stroke: {
    color: '#0066CC',
    stroke_width: 2.5,
    opacity: 1.0,
    stroke_linecap: 'round',
    stroke_linejoin: 'round',
  },
  supports_color: false,
  supports_variable_width: false,
  supports_opacity: false,
  color_palette: null,
};

export const PAINT_STYLE: DrawingStyleConfig = {
  type: 'paint',
  name: 'Paint',
  description: 'Full color painting style with expressive brush strokes',
  agent_stroke: {
    color: '#1a1a2e',
    stroke_width: 8.0, // Thicker for brush effect
    opacity: 0.85,
    stroke_linecap: 'round',
    stroke_linejoin: 'round',
  },
  human_stroke: {
    color: '#e94560',
    stroke_width: 8.0, // Thicker for brush effect
    opacity: 0.85,
    stroke_linecap: 'round',
    stroke_linejoin: 'round',
  },
  supports_color: true,
  supports_variable_width: true,
  supports_opacity: true,
  color_palette: [
    '#1a1a2e', // Dark (near black)
    '#e94560', // Rose/crimson
    '#7b68ee', // Violet
    '#4ecdc4', // Teal
    '#ffd93d', // Gold
    '#ff6b6b', // Coral
    '#4ade80', // Green
    '#3b82f6', // Blue
    '#f97316', // Orange
    '#a855f7', // Purple
    '#ffffff', // White
  ],
};

export const DRAWING_STYLES: Record<DrawingStyleType, DrawingStyleConfig> = {
  plotter: PLOTTER_STYLE,
  paint: PAINT_STYLE,
};

export function getStyleConfig(styleType: DrawingStyleType): DrawingStyleConfig {
  return DRAWING_STYLES[styleType];
}

// Brush preset types for paint-like rendering
export type BrushName =
  | 'oil_round'
  | 'oil_flat'
  | 'oil_filbert'
  | 'watercolor'
  | 'dry_brush'
  | 'palette_knife'
  | 'ink'
  | 'pencil'
  | 'charcoal'
  | 'marker'
  | 'airbrush'
  | 'splatter';

export interface BrushPreset {
  name: BrushName;
  displayName: string;
  description: string;
  // Bristle rendering (sub-strokes)
  bristleCount: number;
  bristleSpread: number;
  bristleOpacity: number;
  bristleWidthRatio: number;
  // Main stroke
  mainOpacity: number;
  baseWidth: number;
  // Stroke shape
  taper: number;
  pressureResponse: number;
  // Edge effects
  edgeNoise: number;
  wetEdges: number;
  // Smoothing
  smoothing: number;
}

// Brush preset definitions (mirrors backend)
export const BRUSH_PRESETS: Record<BrushName, BrushPreset> = {
  oil_round: {
    name: 'oil_round',
    displayName: 'Oil Round',
    description: 'Classic round brush with visible bristle texture',
    bristleCount: 3,
    bristleSpread: 0.7,
    bristleOpacity: 0.14,
    bristleWidthRatio: 0.35,
    mainOpacity: 0.75,
    baseWidth: 10.0,
    taper: 0.7,
    pressureResponse: 0.5,
    edgeNoise: 0,
    wetEdges: 0,
    smoothing: 0.6,
  },
  oil_flat: {
    name: 'oil_flat',
    displayName: 'Oil Flat',
    description: 'Flat brush with parallel bristle marks',
    bristleCount: 4,
    bristleSpread: 0.5,
    bristleOpacity: 0.13,
    bristleWidthRatio: 0.25,
    mainOpacity: 0.8,
    baseWidth: 12.0,
    taper: 0.3,
    pressureResponse: 0.3,
    edgeNoise: 0,
    wetEdges: 0,
    smoothing: 0.4,
  },
  oil_filbert: {
    name: 'oil_filbert',
    displayName: 'Oil Filbert',
    description: 'Rounded flat brush for organic shapes',
    bristleCount: 3,
    bristleSpread: 0.6,
    bristleOpacity: 0.14,
    bristleWidthRatio: 0.3,
    mainOpacity: 0.78,
    baseWidth: 10.0,
    taper: 0.6,
    pressureResponse: 0.4,
    edgeNoise: 0,
    wetEdges: 0,
    smoothing: 0.7,
  },
  watercolor: {
    name: 'watercolor',
    displayName: 'Watercolor',
    description: 'Translucent with soft edges, colors pool at ends',
    bristleCount: 0,
    bristleSpread: 0,
    bristleOpacity: 0,
    bristleWidthRatio: 0,
    mainOpacity: 0.35,
    baseWidth: 14.0,
    taper: 0.5,
    pressureResponse: 0.6,
    edgeNoise: 0.15,
    wetEdges: 0.4,
    smoothing: 0.8,
  },
  dry_brush: {
    name: 'dry_brush',
    displayName: 'Dry Brush',
    description: 'Scratchy, broken strokes with visible gaps',
    bristleCount: 7,
    bristleSpread: 1.0,
    bristleOpacity: 0.22,
    bristleWidthRatio: 0.2,
    mainOpacity: 0.3,
    baseWidth: 10.0,
    taper: 0.4,
    pressureResponse: 0.7,
    edgeNoise: 0,
    wetEdges: 0,
    smoothing: 0.3,
  },
  palette_knife: {
    name: 'palette_knife',
    displayName: 'Palette Knife',
    description: 'Sharp edges, thick paint application',
    bristleCount: 0,
    bristleSpread: 0,
    bristleOpacity: 0,
    bristleWidthRatio: 0,
    mainOpacity: 0.95,
    baseWidth: 16.0,
    taper: 0.1,
    pressureResponse: 0.8,
    edgeNoise: 0.05,
    wetEdges: 0,
    smoothing: 0.2,
  },
  ink: {
    name: 'ink',
    displayName: 'Ink Brush',
    description: 'Pressure-sensitive with elegant taper',
    bristleCount: 0,
    bristleSpread: 0,
    bristleOpacity: 0,
    bristleWidthRatio: 0,
    mainOpacity: 0.9,
    baseWidth: 6.0,
    taper: 0.9,
    pressureResponse: 0.9,
    edgeNoise: 0,
    wetEdges: 0,
    smoothing: 0.7,
  },
  pencil: {
    name: 'pencil',
    displayName: 'Pencil',
    description: 'Thin, consistent lines for sketching',
    bristleCount: 0,
    bristleSpread: 0,
    bristleOpacity: 0,
    bristleWidthRatio: 0,
    mainOpacity: 0.85,
    baseWidth: 2.0,
    taper: 0.2,
    pressureResponse: 0.4,
    edgeNoise: 0,
    wetEdges: 0,
    smoothing: 0.3,
  },
  charcoal: {
    name: 'charcoal',
    displayName: 'Charcoal',
    description: 'Smudgy edges with slight texture',
    bristleCount: 3,
    bristleSpread: 0.4,
    bristleOpacity: 0.3,
    bristleWidthRatio: 0.5,
    mainOpacity: 0.6,
    baseWidth: 5.0,
    taper: 0.4,
    pressureResponse: 0.5,
    edgeNoise: 0.1,
    wetEdges: 0,
    smoothing: 0.5,
  },
  marker: {
    name: 'marker',
    displayName: 'Marker',
    description: 'Solid color with slight edge bleed',
    bristleCount: 0,
    bristleSpread: 0,
    bristleOpacity: 0,
    bristleWidthRatio: 0,
    mainOpacity: 0.75,
    baseWidth: 8.0,
    taper: 0.15,
    pressureResponse: 0.1,
    edgeNoise: 0,
    wetEdges: 0.2,
    smoothing: 0.4,
  },
  airbrush: {
    name: 'airbrush',
    displayName: 'Airbrush',
    description: 'Very soft edges for gradients',
    bristleCount: 0,
    bristleSpread: 0,
    bristleOpacity: 0,
    bristleWidthRatio: 0,
    mainOpacity: 0.25,
    baseWidth: 20.0,
    taper: 0.0,
    pressureResponse: 0.3,
    edgeNoise: 0,
    wetEdges: 0,
    smoothing: 0.9,
  },
  splatter: {
    name: 'splatter',
    displayName: 'Splatter',
    description: 'Random dots around stroke path',
    bristleCount: 20,
    bristleSpread: 2.0,
    bristleOpacity: 0.6,
    bristleWidthRatio: 0.15,
    mainOpacity: 0.5,
    baseWidth: 8.0,
    taper: 0.3,
    pressureResponse: 0.2,
    edgeNoise: 0.3,
    wetEdges: 0,
    smoothing: 0.5,
  },
};

// List of all brush names for iteration
export const BRUSH_NAMES: BrushName[] = [
  'oil_round',
  'oil_flat',
  'oil_filbert',
  'watercolor',
  'dry_brush',
  'palette_knife',
  'ink',
  'pencil',
  'charcoal',
  'marker',
  'airbrush',
  'splatter',
];

// Default brush for paint mode
export const DEFAULT_BRUSH: BrushName = 'oil_round';

export function getBrushPreset(name: BrushName): BrushPreset {
  return BRUSH_PRESETS[name];
}

export interface Path {
  type: PathType;
  points: Point[];
  d?: string; // SVG path d-string (for type='svg')
  author?: 'agent' | 'human';
  // Style properties (optional - use style defaults if not set)
  color?: string; // Hex color
  stroke_width?: number; // Stroke width
  opacity?: number; // 0-1 alpha
  // Brush preset (paint mode only)
  brush?: BrushName; // Brush preset name for paint-like rendering
}

/**
 * Get the effective style for a path, merging with style defaults.
 */
export function getEffectiveStyle(path: Path, styleConfig: DrawingStyleConfig): StrokeStyle {
  const author = path.author || 'agent';
  const defaultStyle = author === 'agent' ? styleConfig.agent_stroke : styleConfig.human_stroke;

  // In plotter mode, always use defaults
  if (styleConfig.type === 'plotter') {
    return defaultStyle;
  }

  // In paint mode, allow overrides
  return {
    color: path.color && styleConfig.supports_color ? path.color : defaultStyle.color,
    stroke_width:
      path.stroke_width && styleConfig.supports_variable_width
        ? path.stroke_width
        : defaultStyle.stroke_width,
    opacity:
      typeof path.opacity === 'number' && styleConfig.supports_opacity
        ? path.opacity
        : defaultStyle.opacity,
    stroke_linecap: defaultStyle.stroke_linecap,
    stroke_linejoin: defaultStyle.stroke_linejoin,
  };
}

/**
 * Get the effective style for an in-progress agent stroke.
 * Applies overrides from agentStrokeStyle only when the style mode supports them.
 */
export function getEffectiveAgentStrokeStyle(
  styleConfig: DrawingStyleConfig,
  agentStrokeStyle: Partial<StrokeStyle> | null | undefined
): StrokeStyle {
  return {
    color:
      styleConfig.supports_color && agentStrokeStyle?.color
        ? agentStrokeStyle.color
        : styleConfig.agent_stroke.color,
    stroke_width:
      styleConfig.supports_variable_width && agentStrokeStyle?.stroke_width
        ? agentStrokeStyle.stroke_width
        : styleConfig.agent_stroke.stroke_width,
    opacity:
      styleConfig.supports_opacity && typeof agentStrokeStyle?.opacity === 'number'
        ? agentStrokeStyle.opacity
        : styleConfig.agent_stroke.opacity,
    stroke_linecap: styleConfig.agent_stroke.stroke_linecap,
    stroke_linejoin: styleConfig.agent_stroke.stroke_linejoin,
  };
}

// Agent status
export type AgentStatus = 'idle' | 'thinking' | 'executing' | 'drawing' | 'paused' | 'error';

// Shared status labels for consistent UI across components
export const STATUS_LABELS: Record<AgentStatus, string> = {
  idle: 'Ready',
  thinking: 'Thinking',
  executing: 'Running Code',
  drawing: 'Drawing',
  paused: 'Paused',
  error: 'Error',
};

// Animation constants
export const PULSE_DURATION_MS = 800;

// Application state
export interface CanvasState {
  width: number;
  height: number;
  strokes: Path[];
  drawingStyle: DrawingStyleType;
}

export interface AgentState {
  status: AgentStatus;
  monologue: string;
  pieceNumber: number;
}

export interface AppState {
  canvas: CanvasState;
  agent: AgentState;
}

// WebSocket messages - Server to Client
export interface HumanStrokeMessage {
  type: 'human_stroke';
  path: Path;
}

export interface PausedMessage {
  type: 'paused';
  paused: boolean;
}

export interface ClearMessage {
  type: 'clear';
}

export interface GalleryEntry {
  id: string;
  stroke_count: number;
  created_at: string;
  piece_number: number;
  drawing_style?: DrawingStyleType; // Style used for this piece (defaults to plotter)
  thumbnail_token?: string; // Capability token for thumbnail access
  title?: string; // Piece title (set by agent via name_piece tool)
}

// Backwards compatibility alias
export type SavedCanvas = GalleryEntry;

export interface NewCanvasMessage {
  type: 'new_canvas';
  saved_id: string | null;
}

export interface GalleryUpdateMessage {
  type: 'gallery_update';
  canvases: SavedCanvas[];
}

export interface LoadCanvasMessage {
  type: 'load_canvas';
  strokes: Path[];
  piece_number: number;
  drawing_style?: DrawingStyleType;
  style_config?: DrawingStyleConfig;
}

export interface InitMessage {
  type: 'init';
  strokes: Path[];
  gallery: SavedCanvas[];
  status: AgentStatus;
  paused: boolean;
  piece_number: number;
  monologue: string;
  drawing_style?: DrawingStyleType;
  style_config?: DrawingStyleConfig;
}

export interface PieceStateMessage {
  type: 'piece_state';
  number: number;
  completed: boolean;
}

// New message types for real-time status streaming
export interface ThinkingDeltaMessage {
  type: 'thinking_delta';
  text: string; // Only the new text since last message
  iteration: number;
}

export type ToolName =
  | 'draw_paths'
  | 'generate_svg'
  | 'view_canvas'
  | 'mark_piece_done'
  | 'imagine'
  | 'sign_canvas'
  | 'name_piece';

/**
 * Human-readable display names for tools.
 */
export const TOOL_DISPLAY_NAMES: Record<ToolName, string> = {
  draw_paths: 'drawing paths',
  generate_svg: 'generating SVG',
  view_canvas: 'viewing canvas',
  mark_piece_done: 'marking done',
  imagine: 'imagining',
  sign_canvas: 'signing',
  name_piece: 'naming piece',
};

export interface CodeExecutionMessage {
  type: 'code_execution';
  status: 'started' | 'completed';
  tool_name?: ToolName | null;
  tool_input?: Record<string, unknown> | null;
  stdout?: string | null;
  stderr?: string | null;
  return_code?: number | null;
  iteration: number;
}

export interface ErrorMessage {
  type: 'error';
  message: string;
  details?: string | null;
}

export interface IterationMessage {
  type: 'iteration';
  current: number;
  max: number;
}

export interface AgentStrokesReadyMessage {
  type: 'agent_strokes_ready';
  count: number;
  batch_id: number;
  piece_number: number;
}

/**
 * A pending stroke ready for client-side rendering.
 * Contains the original path and pre-interpolated points.
 */
export interface PendingStroke {
  batch_id: number;
  path: Path;
  points: Point[]; // Pre-interpolated points for animation
}

export type ServerMessage =
  | HumanStrokeMessage
  | ThinkingDeltaMessage
  | PausedMessage
  | ClearMessage
  | NewCanvasMessage
  | GalleryUpdateMessage
  | LoadCanvasMessage
  | InitMessage
  | PieceStateMessage
  | CodeExecutionMessage
  | ErrorMessage
  | IterationMessage
  | AgentStrokesReadyMessage;

// WebSocket messages - Client to Server
export interface ClientStrokeMessage {
  type: 'stroke';
  points: Point[];
}

export interface ClientNudgeMessage {
  type: 'nudge';
  text: string;
}

export interface ClientClearMessage {
  type: 'clear';
}

export interface ClientPauseMessage {
  type: 'pause';
}

export interface ClientResumeMessage {
  type: 'resume';
  direction?: string; // Optional direction/prompt for the agent
}

export interface ClientNewCanvasMessage {
  type: 'new_canvas';
  direction?: string; // Optional direction for the agent
  drawing_style?: DrawingStyleType; // Optional style for the new canvas
}

export interface ClientLoadCanvasMessage {
  type: 'load_canvas';
  piece_number: number;
}

export interface ClientAnimationDoneMessage {
  type: 'animation_done';
  batch_id: number;
}

export type ClientMessage =
  | ClientStrokeMessage
  | ClientNudgeMessage
  | ClientClearMessage
  | ClientPauseMessage
  | ClientResumeMessage
  | ClientNewCanvasMessage
  | ClientLoadCanvasMessage
  | ClientAnimationDoneMessage;

// Agent message types for MessageStream component
export type AgentMessageType =
  | 'thinking'
  | 'thinking_delta'
  | 'error'
  | 'piece_complete'
  | 'code_execution'
  | 'iteration';

export interface AgentMessage {
  id: string;
  type: AgentMessageType;
  text: string;
  timestamp: number;
  iteration?: number; // For iteration-aware messages
  status?: 'started' | 'completed'; // For code_execution messages
  metadata?: {
    tool_name?: ToolName | null;
    tool_input?: Record<string, unknown> | null;
    stdout?: string | null;
    stderr?: string | null;
    return_code?: number | null;
    piece_number?: number;
    current_iteration?: number;
    max_iterations?: number;
  };
}

// Canvas dimensions
export const CANVAS_WIDTH = 800;
export const CANVAS_HEIGHT = 600;
export const CANVAS_ASPECT_RATIO = CANVAS_WIDTH / CANVAS_HEIGHT;
