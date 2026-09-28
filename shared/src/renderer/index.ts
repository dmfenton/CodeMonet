/**
 * Renderer abstraction module.
 *
 * Provides a common interface for SVG and Skia renderers,
 * allowing blue-green deployment between rendering backends.
 */

// Types
export type { RendererType, RendererConfig, RendererProps, RendererContextValue } from './types';

// Configuration
export {
  DEFAULT_RENDERER_CONFIG,
  FREEHAND_SVG_CONFIG,
  SKIA_PAINTERLY_CONFIG,
  getDefaultConfigForRenderer,
  isRendererAvailable,
} from './config';

// Perfect-freehand stroke processing
export type { FreehandStrokeOptions } from './freehand';
export {
  DEFAULT_FREEHAND_OPTIONS,
  PAINTERLY_FREEHAND_OPTIONS,
  brushPresetToFreehandOptions,
  getFreehandOutline,
  outlineToSvgPath,
  pointsToFreehandPath,
  samplePathPoints,
  getBristleOutlines,
} from './freehand';

// Stamp-based painterly stroke model (port of server painting.py)
export type { Stamp, StampDynamics, StampStrokeStyle, SpriteAlpha, Rgb, Rng } from './stamping';
export {
  SPRITE_VARIANTS,
  SPRITE_BASE_WIDTH,
  STAMP_DYNAMICS,
  computeStrokeStamps,
  generateSpriteAlpha,
  getStampDynamics,
  hexToRgb,
  mulberry32,
  strokeSeed,
} from './stamping';

// Performance stream (live pixel deltas from the paint run)
export type { PerformanceFrame, PerformanceMeta, PerformancePatch } from './performance';
export {
  PAINTING_FINAL_FILE,
  PERFORMANCE_FILE,
  PERFORMANCE_MAX_BEHIND_MS,
  PERFORMANCE_ORDER_SCALE,
  PerformanceParser,
  decodePatchIndex,
  paintingAssetUrl,
  patchFits,
  patchOrderThreshold,
  playbackRate,
} from './performance';
