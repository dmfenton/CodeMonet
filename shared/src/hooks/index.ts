/**
 * Shared React hooks.
 */

export { useCanvas } from './useCanvas';
export type { UseCanvasReturn } from './useCanvas';

export { usePerformer } from './usePerformer';
export type { UsePerformerOptions } from './usePerformer';

export { usePendingStrokes } from './usePendingStrokes';
export type { UsePendingStrokesOptions } from './usePendingStrokes';

export { useLiveStatus, getStatusLabel } from './useLiveStatus';
export type {
  LiveStatusDisplay,
  EventDisplay,
  ThinkingDisplay,
  ActiveDisplay,
  InactiveDisplay,
  HiddenDisplay,
} from './useLiveStatus';
