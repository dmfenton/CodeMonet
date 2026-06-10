/**
 * Stamp-based painterly stroke model — TypeScript port of the server's
 * `painting.py` renderer.
 *
 * A brush stroke is decomposed into a sequence of textured, oriented dabs
 * ("stamps"). Each stamp has a position, tangent angle, size (with taper and
 * width wobble), alpha (with paint-load fade), and a broken-color tint
 * (per-stamp HSV jitter). Platform renderers draw the stamps:
 *  - web: 2D canvas drawImage with tinted sprite bitmaps
 *  - app: Skia Atlas with per-sprite RSXform transforms and tint colors
 *
 * Sprite textures (bristle streaks, ragged edges) are generated here as
 * alpha maps so both platforms share one look. Blur-like softness is baked
 * into the sprite falloff (`soften`) instead of a post-blur pass.
 */

import type { BrushName, Point } from '../types';

// ---------------------------------------------------------------------------
// Deterministic PRNG (mulberry32) — renders must be repeatable across frames
// ---------------------------------------------------------------------------

export type Rng = () => number;

export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Stable seed from stroke geometry (mirrors the server's approach). */
export function strokeSeed(points: Point[], width: number): number {
  let sum = 0;
  for (const p of points) {
    sum += p.x * 17.0 + p.y * 31.0;
  }
  return (Math.floor(sum) ^ Math.floor(width * 7)) >>> 0;
}

// ---------------------------------------------------------------------------
// Brush dynamics (mirrors server painting.py _DYNAMICS)
// ---------------------------------------------------------------------------

export interface StampDynamics {
  /** stamp spacing as fraction of width */
  spacing: number;
  /** stamp length / stamp width */
  aspect: number;
  /** bristle streak rows in the sprite (0 = smooth) */
  streaks: number;
  /** 0 = smooth dab, 1 = strong bristle rails */
  streakContrast: number;
  /** raggedness of the sprite outline */
  edgeRough: number;
  /** per-stamp alpha breakup (0-1) */
  dryness: number;
  /** paint depletion toward stroke end (0-1) */
  loadFade: number;
  /** per-stamp hue wobble (fraction of wheel) */
  hueJitter: number;
  satJitter: number;
  valJitter: number;
  /** end taper strength */
  taper: number;
  /** low-frequency width variation */
  widthWobble: number;
  /** softness of sprite falloff (replaces server post-blur) */
  soften: number;
  /** watercolor-style edge darkening (0-1) */
  wetEdge: number;
}

const DEFAULT_DYNAMICS: StampDynamics = {
  spacing: 0.35,
  aspect: 1.7,
  streaks: 5,
  streakContrast: 0.45,
  edgeRough: 0.35,
  dryness: 0.12,
  loadFade: 0.25,
  hueJitter: 0.012,
  satJitter: 0.1,
  valJitter: 0.08,
  taper: 0.6,
  widthWobble: 0.15,
  soften: 0,
  wetEdge: 0,
};

export const STAMP_DYNAMICS: Partial<Record<BrushName, StampDynamics>> = {
  oil_round: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.32,
    aspect: 1.5,
    streaks: 6,
    streakContrast: 0.42,
    edgeRough: 0.3,
    dryness: 0.1,
    taper: 0.65,
  },
  oil_flat: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.3,
    aspect: 1.25,
    streaks: 8,
    streakContrast: 0.75,
    edgeRough: 0.22,
    dryness: 0.14,
    hueJitter: 0.01,
    taper: 0.3,
  },
  oil_filbert: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.34,
    aspect: 1.8,
    streaks: 6,
    streakContrast: 0.5,
    edgeRough: 0.35,
    dryness: 0.12,
    hueJitter: 0.014,
    taper: 0.55,
  },
  dry_brush: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.3,
    aspect: 1.9,
    streaks: 9,
    streakContrast: 0.95,
    edgeRough: 0.6,
    dryness: 0.55,
    loadFade: 0.5,
    hueJitter: 0.01,
    taper: 0.5,
    widthWobble: 0.3,
  },
  palette_knife: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.42,
    aspect: 2.6,
    streaks: 3,
    streakContrast: 0.35,
    edgeRough: 0.5,
    dryness: 0.2,
    loadFade: 0.45,
    hueJitter: 0.008,
    satJitter: 0.06,
    valJitter: 0.12,
    taper: 0.15,
    widthWobble: 0.1,
  },
  watercolor: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.4,
    aspect: 1.6,
    streaks: 0,
    streakContrast: 0,
    edgeRough: 0.45,
    dryness: 0.05,
    loadFade: 0.15,
    hueJitter: 0.01,
    satJitter: 0.12,
    valJitter: 0.05,
    taper: 0.5,
    widthWobble: 0.28,
    soften: 0.6,
    wetEdge: 0.55,
  },
  airbrush: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.45,
    aspect: 1.0,
    streaks: 0,
    streakContrast: 0,
    edgeRough: 0,
    dryness: 0,
    loadFade: 0,
    hueJitter: 0.004,
    satJitter: 0.04,
    valJitter: 0.03,
    taper: 0,
    widthWobble: 0.05,
    soften: 1.0,
  },
  charcoal: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.32,
    aspect: 1.4,
    streaks: 5,
    streakContrast: 0.55,
    edgeRough: 0.5,
    dryness: 0.45,
    loadFade: 0.3,
    hueJitter: 0,
    satJitter: 0.04,
    valJitter: 0.1,
    taper: 0.4,
    widthWobble: 0.25,
  },
  ink: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.28,
    aspect: 1.4,
    streaks: 0,
    streakContrast: 0,
    edgeRough: 0.15,
    dryness: 0.06,
    loadFade: 0.2,
    hueJitter: 0,
    satJitter: 0.02,
    valJitter: 0.04,
    taper: 0.9,
    widthWobble: 0.18,
  },
  pencil: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.3,
    aspect: 1.2,
    streaks: 2,
    streakContrast: 0.4,
    edgeRough: 0.3,
    dryness: 0.35,
    loadFade: 0.1,
    hueJitter: 0,
    satJitter: 0.02,
    valJitter: 0.06,
    taper: 0.25,
    widthWobble: 0.12,
  },
  marker: {
    ...DEFAULT_DYNAMICS,
    spacing: 0.3,
    aspect: 1.3,
    streaks: 0,
    streakContrast: 0,
    edgeRough: 0.12,
    dryness: 0.04,
    loadFade: 0.08,
    hueJitter: 0.004,
    satJitter: 0.03,
    valJitter: 0.03,
    taper: 0.15,
    widthWobble: 0.06,
    soften: 0.25,
  },
  splatter: {
    ...DEFAULT_DYNAMICS,
    spacing: 1.6,
    aspect: 0.9,
    streaks: 0,
    streakContrast: 0,
    edgeRough: 0.7,
    dryness: 0.3,
    loadFade: 0.2,
    hueJitter: 0.02,
    satJitter: 0.12,
    valJitter: 0.12,
    taper: 0.2,
    widthWobble: 0.8,
  },
};

export function getStampDynamics(brush: BrushName | undefined): StampDynamics {
  if (brush && STAMP_DYNAMICS[brush]) return STAMP_DYNAMICS[brush]!;
  return DEFAULT_DYNAMICS;
}

// ---------------------------------------------------------------------------
// Color helpers (per-stamp broken color)
// ---------------------------------------------------------------------------

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export function hexToRgb(hex: string): Rgb {
  let value = hex.replace('#', '');
  // Mirror the server's tolerance: expand #f0a shorthand.
  if (value.length === 3) {
    value = value
      .split('')
      .map((c) => c + c)
      .join('');
  }
  return {
    r: parseInt(value.slice(0, 2), 16) || 0,
    g: parseInt(value.slice(2, 4), 16) || 0,
    b: parseInt(value.slice(4, 6), 16) || 0,
  };
}

function rgbToHsv(rgb: Rgb): [number, number, number] {
  const r = rgb.r / 255;
  const g = rgb.g / 255;
  const b = rgb.b / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  if (d > 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
    if (h < 0) h += 1;
  }
  const s = max === 0 ? 0 : d / max;
  return [h, s, max];
}

function hsvToRgb(h: number, s: number, v: number): Rgb {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  let r = 0;
  let g = 0;
  let b = 0;
  switch (i % 6) {
    case 0:
      r = v;
      g = t;
      b = p;
      break;
    case 1:
      r = q;
      g = v;
      b = p;
      break;
    case 2:
      r = p;
      g = v;
      b = t;
      break;
    case 3:
      r = p;
      g = q;
      b = v;
      break;
    case 4:
      r = t;
      g = p;
      b = v;
      break;
    default:
      r = v;
      g = p;
      b = q;
      break;
  }
  return { r: Math.round(r * 255), g: Math.round(g * 255), b: Math.round(b * 255) };
}

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

function jitterColor(rgb: Rgb, rng: Rng, dyn: StampDynamics): Rgb {
  const [h, s, v] = rgbToHsv(rgb);
  const h2 = (h + (rng() * 2 - 1) * dyn.hueJitter + 1) % 1;
  const s2 = clamp01(s + (rng() * 2 - 1) * dyn.satJitter * (0.3 + s));
  const v2 = clamp01(v + (rng() * 2 - 1) * dyn.valJitter);
  return hsvToRgb(h2, s2, v2);
}

// ---------------------------------------------------------------------------
// Stamp computation
// ---------------------------------------------------------------------------

export const SPRITE_VARIANTS = 4;
const MAX_STAMPS_PER_STROKE = 700;

export interface Stamp {
  x: number;
  y: number;
  /** tangent angle in radians (screen coords, y-down) */
  angle: number;
  /** stamp length along the stroke direction */
  length: number;
  /** stamp width across the stroke */
  width: number;
  /** stamp alpha (0-1), already includes load fade and stroke opacity */
  alpha: number;
  /** sprite variant index (0..SPRITE_VARIANTS-1) */
  variant: number;
  /** broken-color tint for this stamp */
  color: Rgb;
}

interface ResampledPoint {
  x: number;
  y: number;
  angle: number;
}

function resample(points: Point[], spacing: number): ResampledPoint[] {
  if (points.length < 2) {
    const p = points[0];
    return p ? [{ x: p.x, y: p.y, angle: 0 }] : [];
  }
  const segLen: number[] = [];
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const len = Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.y - points[i - 1]!.y);
    segLen.push(len);
    total += len;
  }
  const effSpacing = Math.max(spacing, total / MAX_STAMPS_PER_STROKE, 0.75);
  const n = Math.max(2, Math.floor(total / effSpacing) + 1);

  const out: ResampledPoint[] = [];
  let j = 0;
  let cum = 0;
  for (let k = 0; k < n; k++) {
    const target = (k / (n - 1)) * total;
    while (j < segLen.length - 1 && cum + segLen[j]! < target) {
      cum += segLen[j]!;
      j++;
    }
    const denom = Math.max(1e-6, segLen[j]!);
    const f = (target - cum) / denom;
    const p0 = points[j]!;
    const p1 = points[j + 1]!;
    out.push({
      x: p0.x + (p1.x - p0.x) * f,
      y: p0.y + (p1.y - p0.y) * f,
      angle: Math.atan2(p1.y - p0.y, p1.x - p0.x),
    });
  }
  return out;
}

/** Low-frequency multiplicative noise around 1.0 (smoothstep between knots). */
function smoothNoise(rng: Rng, n: number, scale: number): number[] {
  if (n <= 0) return [];
  const knots = Math.max(2, Math.floor(n / 6));
  const vals: number[] = [];
  for (let i = 0; i < knots; i++) vals.push(rng() * 2 - 1);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = (i / Math.max(1, n - 1)) * (knots - 1);
    const k = Math.min(Math.floor(t), knots - 2);
    let f = t - k;
    f = f * f * (3 - 2 * f);
    out.push(1 + (vals[k]! * (1 - f) + vals[k + 1]! * f) * scale);
  }
  return out;
}

function taperProfile(t: number, taper: number): number {
  let ease = 1;
  if (t < 0.18) {
    const head = Math.min(1, t / 0.18);
    ease = head * (0.4 + 0.6 * head);
  } else if (t > 0.7) {
    const tail = Math.min(1, (1 - t) / 0.3);
    ease = tail * (0.4 + 0.6 * tail);
  }
  return 1 - taper * (1 - ease);
}

export interface StampStrokeStyle {
  color: string;
  strokeWidth: number;
  opacity: number;
}

/**
 * Decompose a stroke (already sampled to points) into stamps.
 * Deterministic for a given (points, style) pair.
 */
export function computeStrokeStamps(
  points: Point[],
  style: StampStrokeStyle,
  brush: BrushName | undefined
): Stamp[] {
  if (points.length < 2 || style.opacity <= 0) return [];
  const dyn = getStampDynamics(brush);
  const width = Math.max(1.5, style.strokeWidth);
  const rng = mulberry32(strokeSeed(points, width));
  const base = hexToRgb(style.color);

  const stamps = resample(points, Math.max(1.0, width * dyn.spacing));
  const n = stamps.length;
  if (n === 0) return [];
  const wobble = smoothNoise(rng, n, dyn.widthWobble);

  // Short marks (dabs) should not taper or deplete like long strokes.
  const lengthFactor = Math.min(1, n / 10);
  const taper = dyn.taper * lengthFactor;
  const loadFade = dyn.loadFade * lengthFactor;

  // Per-stamp alpha calibrated so accumulated coverage approximates the
  // requested stroke opacity despite stamp overlap.
  const overlap = Math.max(1, (dyn.aspect / dyn.spacing) * 0.45);
  const target = Math.min(0.985, style.opacity);
  const stampAlpha = 1 - Math.pow(1 - target, 1 / overlap);

  const out: Stamp[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / Math.max(1, n - 1);
    const w = width * taperProfile(t, taper) * wobble[i]!;
    if (w < 0.6) continue;

    const load = 1 - loadFade * Math.pow(t, 1.3) * (0.7 + rng() * 0.3);
    let alpha = stampAlpha * load;
    if (dyn.wetEdge > 0 && (t < 0.08 || t > 0.92)) {
      alpha = Math.min(1, alpha * (1 + dyn.wetEdge));
    }
    if (dyn.dryness > 0) {
      // No shared canvas-tooth map on the client; approximate dry breakup
      // with per-stamp alpha noise that gets stronger as the load drops.
      const dry = dyn.dryness * (0.5 + 0.5 * (1 - load));
      alpha *= Math.max(0, 1 - dry * rng() * 1.6);
    }
    const color = jitterColor(base, rng, dyn);
    if (alpha <= 0.004) continue;

    const stamp = stamps[i]!;
    out.push({
      x: stamp.x,
      y: stamp.y,
      angle: stamp.angle,
      length: w * dyn.aspect * 1.1 + 1,
      width: w * 1.1 + 1,
      alpha,
      variant: (i * 7) % SPRITE_VARIANTS,
      color,
    });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Sprite generation (alpha maps shared by both platforms)
// ---------------------------------------------------------------------------

export const SPRITE_BASE_WIDTH = 48;

export interface SpriteAlpha {
  width: number;
  height: number;
  /** row-major alpha values in [0,1], length = width*height */
  data: Float32Array;
}

/** Bilinear upsample of a coarse noise grid to (w, h). */
function upsampleNoise(rng: Rng, coarseW: number, coarseH: number, w: number, h: number): Float32Array {
  const coarse = new Float32Array(coarseW * coarseH);
  for (let i = 0; i < coarse.length; i++) coarse[i] = rng();
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const gy = (y / Math.max(1, h - 1)) * (coarseH - 1);
    const y0 = Math.min(Math.floor(gy), coarseH - 2);
    const fy = gy - y0;
    for (let x = 0; x < w; x++) {
      const gx = (x / Math.max(1, w - 1)) * (coarseW - 1);
      const x0 = Math.min(Math.floor(gx), coarseW - 2);
      const fx = gx - x0;
      const a = coarse[y0 * coarseW + x0]!;
      const b = coarse[y0 * coarseW + x0 + 1]!;
      const c = coarse[(y0 + 1) * coarseW + x0]!;
      const d = coarse[(y0 + 1) * coarseW + x0 + 1]!;
      out[y * w + x] = a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy;
    }
  }
  return out;
}

/**
 * Generate the horizontal base dab texture for a brush variant.
 * Mirrors the server's `_base_sprite`. Cached by callers.
 */
export function generateSpriteAlpha(brush: BrushName | undefined, variant: number): SpriteAlpha {
  const dyn = getStampDynamics(brush);
  const width = SPRITE_BASE_WIDTH;
  const length = Math.max(8, Math.round(width * dyn.aspect));
  // Stable seed per (brush, variant)
  let seed = variant * 7919 + 17;
  const name = brush ?? 'default';
  for (let i = 0; i < name.length; i++) seed = (seed * 31 + name.charCodeAt(i)) >>> 0;
  const rng = mulberry32(seed);

  const data = new Float32Array(width * length === 0 ? 0 : width * length);
  // Softness widens the falloff (replaces the server's post-blur).
  const plateau = 2.2 - dyn.soften * 1.4;
  const exponent = 0.6 + dyn.soften * 0.9;

  const edgeNoise = dyn.edgeRough > 0 ? upsampleNoise(rng, 8, 6, length, width) : null;

  const rowGain = new Float32Array(width);
  if (dyn.streaks > 0 && dyn.streakContrast > 0) {
    const rows = new Float32Array(dyn.streaks);
    for (let i = 0; i < dyn.streaks; i++) rows[i] = rng();
    for (let y = 0; y < width; y++) {
      const t = (y / Math.max(1, width - 1)) * (dyn.streaks - 1);
      const k = Math.min(Math.floor(t), Math.max(0, dyn.streaks - 2));
      const f = t - k;
      const v = rows[k]! * (1 - f) + rows[Math.min(k + 1, dyn.streaks - 1)]! * f;
      rowGain[y] = 1 - dyn.streakContrast + dyn.streakContrast * (0.35 + 0.9 * v);
    }
  } else {
    rowGain.fill(1);
  }

  for (let y = 0; y < width; y++) {
    const ny = (y / (width - 1)) * 2 - 1;
    for (let x = 0; x < length; x++) {
      const nx = (x / (length - 1)) * 2 - 1;
      const r2 = nx * nx + ny * ny;
      let body = Math.pow(clamp01(plateau * (1 - r2)), exponent);

      if (edgeNoise && dyn.edgeRough > 0) {
        const rim = clamp01((r2 - (1 - dyn.edgeRough * 0.9)) / (dyn.edgeRough * 0.9 + 1e-6));
        body *= 1 - rim * (0.3 + 0.7 * edgeNoise[y * length + x]!);
      }

      // Streaks fade in/out along the dab so rails do not look ruled.
      const run = 0.6 + 0.4 * clamp01(1.2 - Math.abs(nx));
      body *= Math.min(1.3, rowGain[y]! * run);

      // Fine speckle so flats are never airbrush-smooth.
      body *= 0.92 + 0.08 * rng();

      data[y * length + x] = clamp01(body);
    }
  }

  return { width: length, height: width, data };
}
