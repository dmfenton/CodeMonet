/**
 * WebSocket handling exports.
 */

export {
  handleClear,
  handleCodeExecution,
  handleError,
  handleGalleryUpdate,
  handleHumanStroke,
  handleInit,
  handleIteration,
  handleLoadCanvas,
  handleNewCanvas,
  handlePaintingVersion,
  handlePaused,
  handlePieceState,
  handleThinkingDelta,
  routeMessage,
} from './handlers';

export type { DispatchFn } from './handlers';
