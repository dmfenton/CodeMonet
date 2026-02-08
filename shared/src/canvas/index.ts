/**
 * Canvas state management exports.
 */

export {
  canvasReducer,
  deriveAgentStatus,
  hasInProgressEvents,
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
  PerformanceState,
} from './reducer';
