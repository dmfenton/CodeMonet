/**
 * Canvas state management exports.
 */

export {
  canvasReducer,
  deriveAgentStatus,
  hasInProgressEvents,
  hasPainting,
  initialPaintingState,
  initialState,
  initialPerformanceState,
  MAX_MESSAGES,
  MAX_HISTORY,
  MAX_WORDS_PER_CHUNK,
  shouldShowIdleAnimation,
} from './reducer';

export type {
  CanvasAction,
  CanvasHookState,
  PerformanceAction,
  PerformanceItem,
  PaintingState,
  PerformanceState,
} from './reducer';
