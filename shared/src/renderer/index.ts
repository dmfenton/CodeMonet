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

// Program-painting reveal (server-rendered keyframes revealed along footprints)
export type {
  KeyframeSchedule,
  RevealBounds,
  RevealPacing,
  RevealPathSink,
  RevealProgress,
  RevealSchedule,
} from './reveal';
export {
  DEFAULT_REVEAL_PACING,
  PAINTING_FINAL_FILE,
  PAINTING_MANIFEST_FILE,
  buildRevealSchedule,
  paintingAssetUrl,
  parseRevealManifest,
  parseRevealOp,
  revealOpBounds,
  revealProgressAt,
  traceRevealOp,
} from './reveal';
