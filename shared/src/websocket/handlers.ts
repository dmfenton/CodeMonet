/**
 * Message handlers for WebSocket messages.
 *
 * Each handler is a pure function that takes a message and dispatch,
 * and dispatches the appropriate action(s).
 */

import type {
  AgentMessage,
  ClearMessage,
  CodeExecutionMessage,
  ErrorMessage,
  GalleryUpdateMessage,
  HumanStrokeMessage,
  InitMessage,
  IterationMessage,
  LoadCanvasMessage,
  NewCanvasMessage,
  PausedMessage,
  PieceStateMessage,
  ServerMessage,
  ThinkingDeltaMessage,
} from '../types';

import type { CanvasAction } from '../canvas/reducer';
import { generateMessageId } from '../utils';

// Dispatch function type (compatible with React's Dispatch)
export type DispatchFn = (action: CanvasAction) => void;

// Handler type
type MessageHandler<T extends ServerMessage> = (message: T, dispatch: DispatchFn) => void;

// Individual handlers
export const handleHumanStroke: MessageHandler<HumanStrokeMessage> = (message, dispatch) => {
  dispatch({ type: 'ADD_STROKE', path: message.path });
};

export const handleThinkingDelta: MessageHandler<ThinkingDeltaMessage> = (message, dispatch) => {
  // Dual dispatch: both for performance model and legacy state
  // ENQUEUE_WORDS: Goes to performance.buffer for progressive reveal animation
  // APPEND_THINKING: Accumulates in state.thinking for archiving when iteration ends
  dispatch({ type: 'ENQUEUE_WORDS', text: message.text });
  dispatch({ type: 'APPEND_THINKING', text: message.text });
};

export const handlePaused: MessageHandler<PausedMessage> = (message, dispatch) => {
  dispatch({ type: 'SET_PAUSED', paused: message.paused });
};

export const handleIteration: MessageHandler<IterationMessage> = (message, dispatch) => {
  // Archive current thinking to message history before new iteration
  dispatch({ type: 'ARCHIVE_THINKING' });
  dispatch({
    type: 'SET_ITERATION',
    current: message.current,
    max: message.max,
  });
  // Don't add iteration messages to the stream - they're noise
};

// Human-readable labels for tool names
const TOOL_LABELS: Record<string, { started: string; completed: string }> = {
  draw_paths: { started: 'Drawing paths...', completed: 'Paths drawn' },
  generate_svg: { started: 'Generating SVG...', completed: 'SVG generated' },
  view_canvas: { started: 'Viewing canvas...', completed: 'Canvas viewed' },
  mark_piece_done: { started: 'Marking piece done...', completed: 'Piece marked done' },
  imagine: { started: 'Imagining...', completed: 'Imagined' },
  sign_canvas: { started: 'Signing canvas...', completed: 'Canvas signed' },
  name_piece: { started: 'Naming piece...', completed: 'Piece named' },
};

// Get path count from tool input for draw_paths
const getPathCount = (toolInput: Record<string, unknown> | null | undefined): number | null => {
  if (!toolInput) return null;
  const paths = toolInput.paths;
  if (Array.isArray(paths)) {
    return paths.length;
  }
  return null;
};

export const handleCodeExecution: MessageHandler<CodeExecutionMessage> = (message, dispatch) => {
  // NOTE: Don't archive thinking here - let progressive reveal continue
  // while code executes. Strokes wait for isBuffering=false.

  const toolName = message.tool_name ?? 'unknown';
  const labels = TOOL_LABELS[toolName] ?? { started: 'Executing...', completed: 'Completed' };

  const baseMessage: Omit<AgentMessage, 'text'> = {
    id: generateMessageId(),
    type: 'code_execution',
    timestamp: Date.now(),
    iteration: message.iteration,
    status: message.status,
    metadata: {
      tool_name: message.tool_name,
      tool_input: message.tool_input,
    },
  };

  if (message.status === 'started') {
    // Build a more informative message based on tool type
    let text = labels.started;
    if (toolName === 'draw_paths') {
      const pathCount = getPathCount(message.tool_input);
      if (pathCount !== null) {
        text = `Drawing ${pathCount} path${pathCount !== 1 ? 's' : ''}...`;
      }
    }

    const agentMessage = { ...baseMessage, text };
    // Dual dispatch: both for performance model and status derivation
    // ENQUEUE_EVENT: Goes to performance.buffer for event display animation
    // ADD_MESSAGE: Goes to state.messages for hasInProgressEvents (status derivation)
    dispatch({ type: 'ENQUEUE_EVENT', message: agentMessage });
    dispatch({ type: 'ADD_MESSAGE', message: agentMessage });
  } else if (message.status === 'completed') {
    let text = labels.completed;
    if (message.return_code !== 0) {
      text = `${toolName} failed (exit ${message.return_code})`;
    } else if (toolName === 'draw_paths') {
      const pathCount = getPathCount(message.tool_input);
      if (pathCount !== null) {
        text = `Drew ${pathCount} path${pathCount !== 1 ? 's' : ''}`;
      }
    }

    const agentMessage = {
      ...baseMessage,
      text,
      metadata: {
        ...baseMessage.metadata,
        stdout: message.stdout,
        stderr: message.stderr,
        return_code: message.return_code,
      },
    };
    // Dual dispatch (same as started): both for performance model and status derivation
    dispatch({ type: 'ENQUEUE_EVENT', message: agentMessage });
    dispatch({ type: 'ADD_MESSAGE', message: agentMessage });
  }
};

export const handleError: MessageHandler<ErrorMessage> = (message, dispatch) => {
  // Archive thinking before showing error (errors end the turn)
  dispatch({ type: 'ARCHIVE_THINKING' });
  dispatch({
    type: 'ADD_MESSAGE',
    message: {
      id: generateMessageId(),
      type: 'error',
      text: message.message,
      timestamp: Date.now(),
      metadata: {
        stderr: message.details,
      },
    },
  });
};

export const handlePieceState: MessageHandler<PieceStateMessage> = (message, dispatch) => {
  // Update the current piece number
  dispatch({ type: 'SET_PIECE_NUMBER', number: message.number });

  // If piece just completed, show completion message
  if (message.completed) {
    // Archive thinking when piece completes (ends the turn)
    dispatch({ type: 'ARCHIVE_THINKING' });
    dispatch({
      type: 'ADD_MESSAGE',
      message: {
        id: generateMessageId(),
        type: 'piece_complete',
        text: `Piece #${message.number} complete!`,
        timestamp: Date.now(),
        metadata: {
          piece_number: message.number,
        },
      },
    });
  }
};

export const handleClear: MessageHandler<ClearMessage> = (_message, dispatch) => {
  dispatch({ type: 'CLEAR_PERFORMANCE' });
  dispatch({ type: 'CLEAR' });
  dispatch({ type: 'CLEAR_MESSAGES' });
};

export const handleNewCanvas: MessageHandler<NewCanvasMessage> = (_message, dispatch) => {
  dispatch({ type: 'CLEAR_PERFORMANCE' });
  dispatch({ type: 'CLEAR' });
  dispatch({ type: 'CLEAR_MESSAGES' });
};

export const handleGalleryUpdate: MessageHandler<GalleryUpdateMessage> = (message, dispatch) => {
  dispatch({ type: 'SET_GALLERY', canvases: message.canvases });
};

export const handleLoadCanvas: MessageHandler<LoadCanvasMessage> = (message, dispatch) => {
  dispatch({
    type: 'LOAD_CANVAS',
    strokes: message.strokes,
    pieceNumber: message.piece_number,
    drawingStyle: message.drawing_style,
    styleConfig: message.style_config,
  });
};

export const handleInit: MessageHandler<InitMessage> = (message, dispatch) => {
  dispatch({
    type: 'INIT',
    strokes: message.strokes,
    gallery: message.gallery,
    pieceNumber: message.piece_number,
    paused: message.paused,
    drawingStyle: message.drawing_style,
    styleConfig: message.style_config,
  });
};

// Handler registry
const handlers: Partial<Record<ServerMessage['type'], MessageHandler<ServerMessage>>> = {
  human_stroke: handleHumanStroke as MessageHandler<ServerMessage>,
  thinking_delta: handleThinkingDelta as MessageHandler<ServerMessage>,
  paused: handlePaused as MessageHandler<ServerMessage>,
  iteration: handleIteration as MessageHandler<ServerMessage>,
  code_execution: handleCodeExecution as MessageHandler<ServerMessage>,
  error: handleError as MessageHandler<ServerMessage>,
  piece_state: handlePieceState as MessageHandler<ServerMessage>,
  clear: handleClear as MessageHandler<ServerMessage>,
  new_canvas: handleNewCanvas as MessageHandler<ServerMessage>,
  gallery_update: handleGalleryUpdate as MessageHandler<ServerMessage>,
  load_canvas: handleLoadCanvas as MessageHandler<ServerMessage>,
  init: handleInit as MessageHandler<ServerMessage>,
};

/**
 * Route a message to its handler.
 */
export const routeMessage = (message: ServerMessage, dispatch: DispatchFn): void => {
  const handler = handlers[message.type];
  if (handler) {
    handler(message, dispatch);
  }
};
