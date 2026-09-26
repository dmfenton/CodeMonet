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
  handlePieceTitle,
  handleThinkingDelta,
  handleTurnState,
  routeMessage,
} from './handlers';

export type { DispatchFn } from './handlers';
