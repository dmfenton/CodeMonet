/**
 * @drawing-agent/shared
 *
 * Platform-agnostic code shared between React Native and web.
 */

// Types
export * from './types';
export * from './auth/platform';

// Canvas state management
export * from './canvas';

// WebSocket message handling
export * from './websocket';

// React hooks
export * from './hooks';

// Utilities
export {
  boundedConcat,
  boundedPush,
  generateMessageId,
  bionicWord,
  chunkWords,
  splitWords,
  getLastToolCall,
  formatTime,
  getCodeFromInput,
  BIONIC_CHUNK_INTERVAL_MS,
  BIONIC_CHUNK_SIZE,
} from './utils';
export type { BionicWord } from './utils';

// Stroke smoothing utilities
export {
  smoothPolylineToPath,
  polylineToPath,
  calculateVelocityWidths,
  createTaperedStrokePath,
  simplifyPoints,
} from './utils/strokeSmoothing';

// SVG path utilities
export { pathToSvgD, pointsToSvgD, pathToSvgDScaled } from './utils/svgPath';

// Velocity pressure utilities
export { applyVelocityPressure } from './utils/velocityPressure';

// Stroke fetching utilities
export { fetchStrokesWithRetry } from './utils/fetchStrokes';
export type { FetchStrokesOptions } from './utils/fetchStrokes';

// Log forwarding utilities
export {
  initLogForwarder,
  startLogSession,
  forwardLogs,
  stopForwarding,
} from './utils/logForwarder';

// Renderer abstraction
export * from './renderer';
