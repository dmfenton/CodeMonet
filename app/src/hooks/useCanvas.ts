/**
 * Canvas state and touch handling hook.
 * App-specific wrapper with debug logging around shared hook.
 */

import { useCallback, useReducer, useRef } from 'react';

import type { CanvasAction, Path, ServerMessage } from '@code-monet/shared';
import {
  canvasReducer,
  initialState,
  routeMessage,
  type CanvasHookState,
} from '@code-monet/shared';

import { debugReducer, debugThinking } from '../utils/debugLog';

// Re-export types and core hook from shared
export { type CanvasAction, type CanvasHookState, type UseCanvasReturn } from '@code-monet/shared';

// Logging wrapper for reducer - app-specific debug output
function loggingReducer(state: CanvasHookState, action: CanvasAction): CanvasHookState {
  const newState = canvasReducer(state, action);

  // Log relevant state changes
  if (action.type === 'APPEND_THINKING') {
    debugThinking(`APPEND_THINKING: thinking len=${newState.thinking.length}`);
  } else if (action.type === 'ARCHIVE_THINKING') {
    debugThinking(`ARCHIVE_THINKING: total msgs=${newState.messages.length}`);
  } else if (action.type === 'ADD_STROKE') {
    debugReducer(`ADD_STROKE: total strokes=${newState.strokes.length}`);
  } else if (action.type === 'STROKE_PROGRESS') {
    // Only log first point to reduce noise
    if (state.performance.agentStroke.length === 0) {
      debugReducer(`STROKE_PROGRESS: pen DOWN at (${action.point.x.toFixed(0)}, ${action.point.y.toFixed(0)})`);
    }
  } else if (action.type === 'STROKE_COMPLETE') {
    debugReducer(`STROKE_COMPLETE: stroke ${newState.performance.strokeIndex}`);
  } else if (action.type !== 'ADD_POINT') {
    // Log all other actions except noisy ones
    debugReducer(`${action.type}`);
  }

  return newState;
}

/**
 * App-specific useCanvas with debug logging.
 * Wraps the shared hook's reducer with logging instrumentation.
 */
export function useCanvas() {
  const [state, dispatch] = useReducer(loggingReducer, initialState);
  const prevThinkingLenRef = useRef(0);

  // Track thinking changes for debugging
  if (state.thinking.length !== prevThinkingLenRef.current) {
    if (state.thinking.length > 0) {
      debugThinking(`Thinking updated: ${prevThinkingLenRef.current} -> ${state.thinking.length} chars`);
    } else if (prevThinkingLenRef.current > 0) {
      debugThinking(`Thinking cleared (was ${prevThinkingLenRef.current} chars)`);
    }
    prevThinkingLenRef.current = state.thinking.length;
  }

  const handleMessage = useCallback((message: ServerMessage) => {
    routeMessage(message, dispatch);
  }, []);

  const setPaused = useCallback((paused: boolean) => {
    dispatch({ type: 'SET_PAUSED', paused });
  }, []);

  const startStroke = useCallback((x: number, y: number) => {
    dispatch({ type: 'START_STROKE', point: { x, y } });
  }, []);

  const addPoint = useCallback((x: number, y: number) => {
    dispatch({ type: 'ADD_POINT', point: { x, y } });
  }, []);

  const endStroke = useCallback((): Path | null => {
    if (state.currentStroke.length < 2) {
      dispatch({ type: 'END_STROKE' });
      return null;
    }

    const path: Path = {
      type: 'polyline',
      points: state.currentStroke,
    };

    dispatch({ type: 'ADD_STROKE', path });
    dispatch({ type: 'END_STROKE' });

    return path;
  }, [state.currentStroke]);

  const toggleDrawing = useCallback(() => {
    dispatch({ type: 'TOGGLE_DRAWING' });
  }, []);

  const clear = useCallback(() => {
    dispatch({ type: 'CLEAR' });
  }, []);

  const clearMessages = useCallback(() => {
    dispatch({ type: 'CLEAR_MESSAGES' });
  }, []);

  return {
    state,
    dispatch,
    handleMessage,
    startStroke,
    addPoint,
    endStroke,
    toggleDrawing,
    clear,
    clearMessages,
    setPaused,
  };
}

// Re-export screenToCanvas from utils for backwards compatibility
export { screenToCanvas } from '../utils/canvas';
