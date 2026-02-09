/**
 * Canvas state reducer - platform-agnostic state machine.
 */

import type {
  AgentMessage,
  AgentStatus,
  DrawingStyleConfig,
  DrawingStyleType,
  GalleryEntry,
  Path,
  PendingStroke,
  Point,
  StrokeStyle,
} from '../types';
import { PLOTTER_STYLE, getStyleConfig } from '../types';
import { boundedPush } from '../utils';

// Max messages to keep in state to prevent memory issues
export const MAX_MESSAGES = 50;

// Max history items to keep (completed performance items)
export const MAX_HISTORY = 100;

// Max words per chunk before starting a new buffer item (~1.25 seconds at 50ms/word)
export const MAX_WORDS_PER_CHUNK = 25;

// Generate unique message ID for archived thinking
const generateThinkingId = (): string =>
  `thinking_${Date.now()}_${Math.random().toString(36).slice(2)}`;

// Generate unique performance item ID
const generatePerformanceId = (): string =>
  `perf_${Date.now()}_${Math.random().toString(36).slice(2)}`;

// ============================================================================
// Performance Model Types
// ============================================================================

/**
 * Performance item types - things that can be "performed" (animated) on stage.
 */
export type PerformanceItem =
  | { type: 'words'; text: string; id: string }
  | { type: 'event'; message: AgentMessage; id: string }
  | { type: 'strokes'; strokes: PendingStroke[]; id: string };

/**
 * Performance state manages the animation queue for progressive reveal.
 *
 * Data flow:
 *   Server message → ENQUEUE_* → buffer → ADVANCE_STAGE → onStage → STAGE_COMPLETE → history
 *
 * Display reads:
 *   - revealedText: Current text being shown (progressive word reveal)
 *   - agentStroke: Current stroke being drawn (progressive point reveal)
 *   - penPosition/penDown: Cursor position for pen indicator
 */
export interface PerformanceState {
  /** Items waiting in the buffer */
  buffer: PerformanceItem[];
  /** Currently performing item (null = stage is empty) */
  onStage: PerformanceItem | null;
  /** Completed items (for collapsed panel) */
  history: PerformanceItem[];

  // Progress tracking for current item
  /** For 'words': which word we're on */
  wordIndex: number;
  /** For 'strokes': which stroke we're on */
  strokeIndex: number;
  /** For 'strokes': 0-1 within current stroke */
  strokeProgress: number;

  // Live display state (what audience sees now)
  /** Current chunk being revealed */
  revealedText: string;
  /** Current pen location */
  penPosition: Point | null;
  /** Is pen drawing? */
  penDown: boolean;
  /** In-progress stroke points */
  agentStroke: Point[];
  /** Style for in-progress agent stroke */
  agentStrokeStyle: Partial<StrokeStyle> | null;
  /** Where pen is traveling to between strokes (null = not traveling) */
  travelTarget: Point | null;
}

/**
 * Initial performance state.
 */
export const initialPerformanceState: PerformanceState = {
  buffer: [],
  onStage: null,
  history: [],
  wordIndex: 0,
  strokeIndex: 0,
  strokeProgress: 0,
  revealedText: '',
  penPosition: null,
  penDown: false,
  agentStroke: [],
  agentStrokeStyle: null,
  travelTarget: null,
};

/**
 * Canvas state has two text representations:
 *   - thinking: Accumulates for archiving when iteration ends (legacy, used for history)
 *   - performance.revealedText: What's currently displayed (progressive animation)
 *
 * Both exist because:
 *   - thinking enables archiving complete thoughts to message history
 *   - revealedText shows animated partial text during streaming
 */
export interface CanvasHookState {
  // Performance system (new)
  performance: PerformanceState;

  // Strokes
  strokes: Path[];
  currentStroke: Point[];

  // Thinking text (legacy - used for loading history, display via performance.revealedText)
  thinking: string;

  // Event history
  messages: AgentMessage[];

  // Canvas metadata
  pieceNumber: number;
  viewingPiece: number | null; // Which gallery piece is being viewed (null = current)
  drawingEnabled: boolean;
  gallery: GalleryEntry[];
  paused: boolean;
  currentIteration: number;
  maxIterations: number;
  drawingStyle: DrawingStyleType; // Current drawing style
  styleConfig: DrawingStyleConfig; // Full style configuration
  /** Saved canvas state before viewing a gallery piece (for restoring on exit) */
  savedCanvas: {
    strokes: Path[];
    pieceNumber: number;
    drawingStyle: DrawingStyleType;
    styleConfig: DrawingStyleConfig;
  } | null;
}

/**
 * Check if any event is still in-progress (started but not completed).
 *
 * This is the general gate for drawing - we don't start rendering
 * until all preceding events have been shown to the user.
 * Add new event types here as needed.
 */
export function hasInProgressEvents(messages: AgentMessage[]): boolean {
  // Build a set of completed tool executions (by tool_name + iteration)
  const completedTools = new Set<string>();
  for (const m of messages) {
    if (m.type === 'code_execution' && m.status === 'completed') {
      const key = `${m.metadata?.tool_name ?? 'unknown'}_${m.iteration ?? 0}`;
      completedTools.add(key);
    }
  }

  return messages.some((m) => {
    // NOTE: We allow strokes to render while thinking (live message exists)
    // Only block during code execution to ensure tool status is shown first
    // This allows parallel display of thinking + stroke animation

    // Code execution started = check if completed message exists
    if (m.type === 'code_execution' && m.status === 'started') {
      const key = `${m.metadata?.tool_name ?? 'unknown'}_${m.iteration ?? 0}`;
      // If we have a completed message for this tool+iteration, it's not in-progress
      if (completedTools.has(key)) return false;
      return true;
    }

    // Add new in-progress event types here as the protocol evolves

    return false;
  });
}

/**
 * Derive agent status from messages and state.
 * Status is computed entirely from messages and state - no server-side status.
 *
 * Status priority (highest to lowest):
 * 1. paused - explicitly paused
 * 2. error - last message is error
 * 3. thinking - words in buffer/onStage
 * 4. executing - code_execution started but not completed
 * 5. drawing - strokes in buffer/onStage
 * 6. idle - default
 */
export function deriveAgentStatus(state: CanvasHookState): AgentStatus {
  // Paused overrides everything
  if (state.paused) return 'paused';

  // Check for error in last message
  const lastMessage = state.messages[state.messages.length - 1];
  if (lastMessage?.type === 'error') return 'error';

  const perf = state.performance;

  // Check performance state for active items
  const hasWordsOnStage = perf.onStage?.type === 'words';
  const hasWordsInBuffer = perf.buffer.some((item) => item.type === 'words');
  const hasStrokesOnStage = perf.onStage?.type === 'strokes';
  const hasStrokesInBuffer = perf.buffer.some((item) => item.type === 'strokes');
  const hasEventOnStage = perf.onStage?.type === 'event';

  // Thinking = words being revealed or waiting
  if (hasWordsOnStage || hasWordsInBuffer) return 'thinking';

  // Executing = event on stage
  if (hasEventOnStage) return 'executing';

  // Any in-progress event blocks drawing and shows as executing (legacy check)
  if (hasInProgressEvents(state.messages)) return 'executing';

  // Drawing = strokes being animated or waiting
  if (hasStrokesOnStage || hasStrokesInBuffer) return 'drawing';

  return 'idle';
}

/**
 * Determine if the idle animation should show.
 * Show only until drawing begins - including when the agent starts drawing
 * (agentStroke has points), not just when the stroke is completed.
 */
export function shouldShowIdleAnimation(state: CanvasHookState): boolean {
  return (
    state.strokes.length === 0 &&
    state.currentStroke.length === 0 &&
    state.performance.agentStroke.length === 0
  );
}

// Performance actions
export type PerformanceAction =
  // Enqueueing (from server messages)
  | { type: 'ENQUEUE_WORDS'; text: string }
  | { type: 'ENQUEUE_EVENT'; message: AgentMessage }
  | { type: 'ENQUEUE_STROKES'; strokes: PendingStroke[] }
  // Stage advancement
  | { type: 'ADVANCE_STAGE' }
  | { type: 'STAGE_COMPLETE' }
  // Progress updates (from animation loop)
  | { type: 'REVEAL_WORD' }
  | { type: 'STROKE_PROGRESS'; point: Point; style?: Partial<StrokeStyle> }
  | { type: 'STROKE_PROGRESS_BATCH'; points: Point[]; style?: Partial<StrokeStyle> }
  | { type: 'STROKE_COMPLETE' }
  // Pen travel (between strokes)
  | { type: 'PEN_TRAVEL_BATCH'; points: Point[] }
  | { type: 'PEN_TRAVEL_COMPLETE' }
  // Control
  | { type: 'CLEAR_PERFORMANCE' };

export type CanvasAction =
  | { type: 'ADD_STROKE'; path: Path }
  | { type: 'SET_STROKES'; strokes: Path[] }
  | { type: 'CLEAR' }
  | { type: 'START_STROKE'; point: Point }
  | { type: 'ADD_POINT'; point: Point }
  | { type: 'END_STROKE' }
  | { type: 'SET_THINKING'; text: string }
  | { type: 'APPEND_THINKING'; text: string }
  | { type: 'ARCHIVE_THINKING' }
  | { type: 'ADD_MESSAGE'; message: AgentMessage }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'TOGGLE_DRAWING' }
  | { type: 'SET_PIECE_NUMBER'; number: number }
  | { type: 'SET_GALLERY'; canvases: GalleryEntry[] }
  | {
      type: 'LOAD_CANVAS';
      strokes: Path[];
      pieceNumber: number;
      drawingStyle?: DrawingStyleType;
      styleConfig?: DrawingStyleConfig;
    }
  | {
      type: 'INIT';
      strokes: Path[];
      gallery: GalleryEntry[];
      pieceNumber: number;
      paused: boolean;
      drawingStyle?: DrawingStyleType;
      styleConfig?: DrawingStyleConfig;
    }
  | { type: 'SET_PAUSED'; paused: boolean }
  | { type: 'SET_ITERATION'; current: number; max: number }
  | { type: 'RESET_TURN' }
  | { type: 'CLEAR_VIEWING' }
  | { type: 'SET_STYLE'; drawingStyle: DrawingStyleType; styleConfig: DrawingStyleConfig }
  // Performance actions (merged into CanvasAction for single reducer)
  | PerformanceAction;

export const initialState: CanvasHookState = {
  // Performance system
  performance: initialPerformanceState,

  // Strokes
  strokes: [],
  currentStroke: [],

  // Thinking (legacy - used for loading history, display via performance.revealedText)
  thinking: '',

  // Messages
  messages: [],

  // Canvas metadata
  pieceNumber: 0,
  viewingPiece: null,
  drawingEnabled: false,
  gallery: [],
  paused: true, // Start paused - status derived from this + messages
  currentIteration: 0,
  maxIterations: 5,
  drawingStyle: 'plotter',
  styleConfig: PLOTTER_STYLE,
  savedCanvas: null,
};

export function canvasReducer(state: CanvasHookState, action: CanvasAction): CanvasHookState {
  switch (action.type) {
    case 'ADD_STROKE':
      return {
        ...state,
        strokes: [...state.strokes, action.path],
      };

    case 'SET_STROKES':
      return { ...state, strokes: action.strokes };

    case 'CLEAR':
      return {
        ...state,
        // Clear performance state
        performance: initialPerformanceState,
        // Clear strokes
        strokes: [],
        currentStroke: [],
        viewingPiece: null,
        savedCanvas: null,
        messages: [],
        thinking: '',
      };

    case 'START_STROKE':
      return { ...state, currentStroke: [action.point] };

    case 'ADD_POINT':
      return { ...state, currentStroke: [...state.currentStroke, action.point] };

    case 'END_STROKE':
      return { ...state, currentStroke: [] };

    // Note: SET_THINKING, APPEND_THINKING, ARCHIVE_THINKING are used for loading history.
    // Live thinking goes through ENQUEUE_WORDS -> performance model -> revealedText.
    case 'SET_THINKING':
      return { ...state, thinking: action.text };

    case 'APPEND_THINKING':
      return { ...state, thinking: state.thinking + action.text };

    case 'ARCHIVE_THINKING': {
      // Move current thinking to message history (used when loading/archiving)
      if (!state.thinking.trim()) {
        return { ...state, thinking: '' };
      }
      const archived: AgentMessage = {
        id: generateThinkingId(),
        type: 'thinking',
        text: state.thinking,
        timestamp: Date.now(),
      };
      return {
        ...state,
        thinking: '',
        messages: boundedPush(state.messages, archived, MAX_MESSAGES),
      };
    }

    case 'ADD_MESSAGE':
      return {
        ...state,
        messages: boundedPush(state.messages, action.message, MAX_MESSAGES),
      };

    case 'CLEAR_MESSAGES':
      return { ...state, messages: [] };

    case 'TOGGLE_DRAWING':
      return { ...state, drawingEnabled: !state.drawingEnabled };

    case 'SET_PIECE_NUMBER':
      return { ...state, pieceNumber: action.number };

    case 'SET_GALLERY':
      return { ...state, gallery: action.canvases };

    case 'LOAD_CANVAS': {
      // If loading a canvas with a different style, update the style config
      const loadedStyle = action.drawingStyle || state.drawingStyle;
      // Use provided styleConfig if available, otherwise compute from style type
      const loadedStyleConfig =
        action.styleConfig ||
        (action.drawingStyle ? getStyleConfig(action.drawingStyle) : state.styleConfig);
      return {
        ...state,
        // Clear performance state when loading from gallery (no animation needed)
        performance: initialPerformanceState,
        strokes: action.strokes,
        currentStroke: [],
        viewingPiece: action.pieceNumber,
        drawingStyle: loadedStyle,
        styleConfig: loadedStyleConfig,
        // Save current canvas state so we can restore when exiting gallery view
        savedCanvas: state.viewingPiece === null ? {
          strokes: state.strokes,
          pieceNumber: state.pieceNumber,
          drawingStyle: state.drawingStyle,
          styleConfig: state.styleConfig,
        } : state.savedCanvas,
      };
    }

    case 'CLEAR_VIEWING': {
      if (state.viewingPiece === null) return state;
      // Restore saved canvas state from before gallery viewing
      if (state.savedCanvas) {
        return {
          ...state,
          viewingPiece: null,
          strokes: state.savedCanvas.strokes,
          pieceNumber: state.savedCanvas.pieceNumber,
          drawingStyle: state.savedCanvas.drawingStyle,
          styleConfig: state.savedCanvas.styleConfig,
          savedCanvas: null,
        };
      }
      return { ...state, viewingPiece: null, savedCanvas: null };
    }

    case 'INIT': {
      // Use provided style or default to plotter
      const initStyle = action.drawingStyle || 'plotter';
      const initStyleConfig = action.styleConfig || getStyleConfig(initStyle);
      return {
        ...state,
        // Reset performance state on init
        performance: initialPerformanceState,
        strokes: action.strokes,
        gallery: action.gallery,
        pieceNumber: action.pieceNumber,
        paused: action.paused,
        viewingPiece: null, // Init shows current canvas
        savedCanvas: null,
        drawingStyle: initStyle,
        styleConfig: initStyleConfig,
        // Reset transient state on init
        messages: [],
        thinking: '',
        currentStroke: [],
      };
    }

    case 'SET_STYLE':
      return {
        ...state,
        drawingStyle: action.drawingStyle,
        styleConfig: action.styleConfig,
      };

    case 'SET_PAUSED':
      return { ...state, paused: action.paused };

    case 'SET_ITERATION':
      return { ...state, currentIteration: action.current, maxIterations: action.max };

    case 'RESET_TURN':
      return { ...state, thinking: '', currentIteration: 0 };

    // ========================================================================
    // Performance Actions
    // ========================================================================

    case 'ENQUEUE_WORDS': {
      const perf = state.performance;
      const lastBufferItem = perf.buffer[perf.buffer.length - 1];

      // Merge with last buffer item if it's words AND under limit
      if (lastBufferItem?.type === 'words') {
        const currentWordCount = lastBufferItem.text.split(/\s+/).filter((w) => w).length;
        if (currentWordCount < MAX_WORDS_PER_CHUNK) {
          const mergedText = lastBufferItem.text + action.text;
          return {
            ...state,
            performance: {
              ...perf,
              buffer: [
                ...perf.buffer.slice(0, -1),
                { type: 'words', text: mergedText, id: lastBufferItem.id },
              ],
            },
          };
        }
        // Over limit - fall through to create new chunk
      }

      // Don't merge with onStage - let current display finish before new text
      // Create new buffer item
      return {
        ...state,
        performance: {
          ...perf,
          buffer: [
            ...perf.buffer,
            { type: 'words', text: action.text, id: generatePerformanceId() },
          ],
        },
      };
    }

    case 'ENQUEUE_EVENT':
      return {
        ...state,
        performance: {
          ...state.performance,
          buffer: [
            ...state.performance.buffer,
            { type: 'event', message: action.message, id: generatePerformanceId() },
          ],
        },
      };

    case 'ENQUEUE_STROKES':
      return {
        ...state,
        performance: {
          ...state.performance,
          buffer: [
            ...state.performance.buffer,
            { type: 'strokes', strokes: action.strokes, id: generatePerformanceId() },
          ],
        },
      };

    case 'ADVANCE_STAGE': {
      const perf = state.performance;
      // Only advance if stage is empty and buffer has items
      const next = perf.buffer[0];
      if (perf.onStage !== null || next === undefined) {
        return state;
      }
      const rest = perf.buffer.slice(1);
      return {
        ...state,
        performance: {
          ...perf,
          buffer: rest,
          onStage: next,
          wordIndex: 0,
          strokeIndex: 0,
          strokeProgress: 0,
          // Reset text when new words chunk starts OR when event starts
          // Events replace thinking text permanently - it doesn't come back
          revealedText: next.type === 'strokes' ? perf.revealedText : '',
          // Reset stroke state when strokes start
          agentStroke: next.type === 'strokes' ? [] : perf.agentStroke,
          agentStrokeStyle: next.type === 'strokes' ? null : perf.agentStrokeStyle,
          travelTarget: null,
        },
      };
    }

    case 'REVEAL_WORD': {
      const perf = state.performance;
      if (perf.onStage?.type !== 'words') return state;
      const words = perf.onStage.text.split(/\s+/).filter((w) => w.length > 0);
      const nextWordIndex = perf.wordIndex + 1;
      const revealedWords = words.slice(0, nextWordIndex);
      return {
        ...state,
        performance: {
          ...perf,
          wordIndex: nextWordIndex,
          revealedText: revealedWords.join(' '),
        },
      };
    }

    case 'STROKE_PROGRESS': {
      const perf = state.performance;
      // Accumulate points when pen is down
      const newAgentStroke = [...perf.agentStroke, action.point];
      // Capture style on first point
      const newStyle =
        perf.agentStroke.length === 0 && action.style ? action.style : perf.agentStrokeStyle;

      return {
        ...state,
        performance: {
          ...perf,
          penPosition: action.point,
          penDown: true,
          agentStroke: newAgentStroke,
          agentStrokeStyle: newStyle,
        },
      };
    }

    case 'STROKE_PROGRESS_BATCH': {
      const perf = state.performance;
      if (action.points.length === 0) return state;

      // Concatenate batch of points efficiently
      const newAgentStroke = perf.agentStroke.concat(action.points);
      // Capture style on first batch
      const newStyle =
        perf.agentStroke.length === 0 && action.style ? action.style : perf.agentStrokeStyle;
      // Pen position is the last point in the batch
      const lastPoint = action.points[action.points.length - 1];

      // Only update pen position if it moved significantly (reduces indicator jitter)
      const MIN_PEN_MOVE = 2; // pixels
      let newPenPosition = perf.penPosition;
      if (lastPoint) {
        if (!perf.penPosition) {
          newPenPosition = lastPoint;
        } else {
          const dx = lastPoint.x - perf.penPosition.x;
          const dy = lastPoint.y - perf.penPosition.y;
          if (Math.sqrt(dx * dx + dy * dy) >= MIN_PEN_MOVE) {
            newPenPosition = lastPoint;
          }
        }
      }

      return {
        ...state,
        performance: {
          ...perf,
          penPosition: newPenPosition,
          penDown: true,
          agentStroke: newAgentStroke,
          agentStrokeStyle: newStyle,
        },
      };
    }

    case 'STROKE_COMPLETE': {
      const perf = state.performance;
      if (perf.onStage?.type !== 'strokes') return state;
      const currentStroke = perf.onStage.strokes[perf.strokeIndex];
      if (!currentStroke) return state;

      // Look ahead to next stroke's first point for pen travel
      const nextStroke = perf.onStage.strokes[perf.strokeIndex + 1];
      const nextFirstPoint = nextStroke?.points[0] ?? null;

      return {
        ...state,
        performance: {
          ...perf,
          strokeIndex: perf.strokeIndex + 1,
          strokeProgress: 0,
          agentStroke: [],
          agentStrokeStyle: null,
          penDown: false,
          travelTarget: nextFirstPoint,
        },
        // Add stroke to main strokes array
        strokes: [...state.strokes, currentStroke.path],
      };
    }

    case 'PEN_TRAVEL_BATCH': {
      const perf = state.performance;
      if (action.points.length === 0) return state;
      const lastPoint = action.points[action.points.length - 1];
      return {
        ...state,
        performance: {
          ...perf,
          penPosition: lastPoint ?? perf.penPosition,
          penDown: false,
        },
      };
    }

    case 'PEN_TRAVEL_COMPLETE': {
      return {
        ...state,
        performance: { ...state.performance, travelTarget: null },
      };
    }

    case 'STAGE_COMPLETE': {
      const perf = state.performance;
      // Bound history size to prevent memory issues
      const newHistory = perf.onStage
        ? [...perf.history, perf.onStage].slice(-MAX_HISTORY)
        : perf.history;

      return {
        ...state,
        performance: {
          ...perf,
          history: newHistory,
          onStage: null,
          penPosition: null,
          penDown: false,
          agentStroke: [],
          agentStrokeStyle: null,
          travelTarget: null,
        },
      };
    }

    case 'CLEAR_PERFORMANCE':
      return {
        ...state,
        performance: initialPerformanceState,
      };

    default:
      return state;
  }
}
