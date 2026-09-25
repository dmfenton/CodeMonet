/**
 * Program-painting reveal: pure, platform-independent playback scheduling
 * and footprint geometry (docs/program-painting.md, "Client playback").
 *
 * The server renders each painting version to keyframe images plus
 * reveal.json (brush footprints). Clients reveal keyframe N over the current
 * picture along those footprints. This module decides *what* is revealed at
 * a given elapsed time; platform layers decide *how* to draw it.
 */

import type {
  AreaRevealOp,
  PaintingVersionRef,
  RevealKeyframe,
  RevealManifest,
  RevealOp,
  StrokeRevealOp,
} from '../types';

// ============================================================================
// Pacing
// ============================================================================

export interface RevealPacing {
  /** Nominal duration of one stroke op. */
  strokeOpMs: number;
  /** Nominal duration of one area op (wipe). */
  areaOpMs: number;
  /** A keyframe is compressed to at most this long. */
  maxKeyframeMs: number;
  /** A whole version is compressed to at most this long. */
  maxVersionMs: number;
}

export const DEFAULT_REVEAL_PACING: RevealPacing = {
  strokeOpMs: 12,
  areaOpMs: 250,
  maxKeyframeMs: 6000,
  maxVersionMs: 45000,
};

// ============================================================================
// Parsing
// ============================================================================

const isFiniteNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/**
 * Validate one raw reveal op. Returns null for malformed ops (they are
 * dropped rather than failing the whole version).
 */
export function parseRevealOp(raw: unknown): RevealOp | null {
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const rest: unknown[] = raw.slice(1);
  if (!rest.every(isFiniteNumber)) return null;
  const nums = rest as number[];
  if (raw[0] === 's') {
    // width + at least one point, whole points only
    if (nums.length < 3 || (nums.length - 1) % 2 !== 0) return null;
    if (nums[0]! <= 0) return null;
    return ['s', ...nums] as StrokeRevealOp;
  }
  if (raw[0] === 'a') {
    if (nums.length !== 4) return null;
    const [x0, y0, x1, y1] = nums as [number, number, number, number];
    return [
      'a',
      Math.min(x0, x1),
      Math.min(y0, y1),
      Math.max(x0, x1),
      Math.max(y0, y1),
    ] as AreaRevealOp;
  }
  return null;
}

/**
 * Validate reveal.json. Returns null when the manifest itself is unusable;
 * malformed individual ops are dropped.
 */
export function parseRevealManifest(raw: unknown): RevealManifest | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const obj = raw as Record<string, unknown>;
  if (!isFiniteNumber(obj.width) || !isFiniteNumber(obj.height)) return null;
  if (obj.width <= 0 || obj.height <= 0 || !Array.isArray(obj.keyframes)) return null;

  const keyframes: RevealKeyframe[] = [];
  for (const kfRaw of obj.keyframes as unknown[]) {
    if (typeof kfRaw !== 'object' || kfRaw === null) return null;
    const kf = kfRaw as Record<string, unknown>;
    if (typeof kf.image !== 'string' || kf.image.length === 0) return null;
    const ops: RevealOp[] = [];
    if (Array.isArray(kf.ops)) {
      for (const opRaw of kf.ops as unknown[]) {
        const op = parseRevealOp(opRaw);
        if (op) ops.push(op);
      }
    }
    keyframes.push({ label: typeof kf.label === 'string' ? kf.label : '', image: kf.image, ops });
  }
  return { width: obj.width, height: obj.height, keyframes };
}

// ============================================================================
// Scheduling
// ============================================================================

export interface KeyframeSchedule {
  /** Keyframe start, ms from version start. */
  startMs: number;
  /** Keyframe end, ms from version start. */
  endMs: number;
  /** End time of each op, ms from version start (ascending). */
  opEndMs: Float64Array;
}

export interface RevealSchedule {
  keyframes: KeyframeSchedule[];
  totalMs: number;
}

const nominalOpMs = (op: RevealOp, pacing: RevealPacing): number =>
  op[0] === 's' ? pacing.strokeOpMs : pacing.areaOpMs;

/**
 * Lay out a version on a timeline: each op gets its nominal duration, a
 * keyframe is compressed to maxKeyframeMs, then the whole version is
 * compressed to maxVersionMs.
 */
export function buildRevealSchedule(
  manifest: RevealManifest,
  pacing: RevealPacing = DEFAULT_REVEAL_PACING
): RevealSchedule {
  const nominal = manifest.keyframes.map((kf) =>
    kf.ops.reduce((sum, op) => sum + nominalOpMs(op, pacing), 0)
  );
  const capped = nominal.map((ms) => Math.min(ms, pacing.maxKeyframeMs));
  const cappedTotal = capped.reduce((a, b) => a + b, 0);
  const versionScale = cappedTotal > pacing.maxVersionMs ? pacing.maxVersionMs / cappedTotal : 1;

  const keyframes: KeyframeSchedule[] = [];
  let t = 0;
  manifest.keyframes.forEach((kf, i) => {
    const nominalMs = nominal[i]!;
    const scale = nominalMs > 0 ? (capped[i]! / nominalMs) * versionScale : 0;
    const startMs = t;
    const opEndMs = new Float64Array(kf.ops.length);
    kf.ops.forEach((op, j) => {
      t += nominalOpMs(op, pacing) * scale;
      opEndMs[j] = t;
    });
    keyframes.push({ startMs, endMs: t, opEndMs });
  });
  return { keyframes, totalMs: t };
}

export type RevealProgress =
  | {
      phase: 'playing';
      /** Keyframe being revealed; all earlier keyframes are complete. */
      keyframe: number;
      /** Ops of this keyframe that are fully revealed. */
      opsDone: number;
      /** The op currently in flight (index === opsDone) and its 0..1 progress. */
      active: { index: number; progress: number } | null;
    }
  | { phase: 'done' };

/** Number of ascending values <= t. */
function countAtOrBefore(values: Float64Array, t: number): number {
  let lo = 0;
  let hi = values.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (values[mid]! <= t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** What should be revealed `elapsedMs` after playback started. */
export function revealProgressAt(schedule: RevealSchedule, elapsedMs: number): RevealProgress {
  if (elapsedMs >= schedule.totalMs) return { phase: 'done' };
  const t = Math.max(0, elapsedMs);
  const k = schedule.keyframes.findIndex((kf) => t < kf.endMs);
  const kf = schedule.keyframes[k];
  if (!kf) return { phase: 'done' };

  const opsDone = countAtOrBefore(kf.opEndMs, t);
  let active: { index: number; progress: number } | null = null;
  if (opsDone < kf.opEndMs.length) {
    const start = opsDone === 0 ? kf.startMs : kf.opEndMs[opsDone - 1]!;
    const dur = kf.opEndMs[opsDone]! - start;
    active = {
      index: opsDone,
      progress: dur > 0 ? Math.min(1, Math.max(0, (t - start) / dur)) : 0,
    };
  }
  return { phase: 'playing', keyframe: k, opsDone, active };
}

// ============================================================================
// Geometry
// ============================================================================

/**
 * Minimal path builder interface (satisfied by web Path2D / CanvasRenderingContext2D
 * and adaptable to Skia paths).
 */
export interface RevealPathSink {
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  arc(x: number, y: number, radius: number, startAngle: number, endAngle: number): void;
  rect(x: number, y: number, w: number, h: number): void;
  closePath(): void;
}

export interface RevealBounds {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Bounding box of an op's footprint (image px). */
export function revealOpBounds(op: RevealOp): RevealBounds {
  if (op[0] === 'a') return { x0: op[1], y0: op[2], x1: op[3], y1: op[4] };
  const r = op[1] / 2;
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (let i = 2; i + 1 < op.length; i += 2) {
    const x = op[i] as number;
    const y = op[i + 1] as number;
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  return { x0: x0 - r, y0: y0 - r, x1: x1 + r, y1: y1 + r };
}

/**
 * Trace an op's footprint as fill geometry (image px), suitable for a
 * non-zero clip/fill:
 *   - stroke: round-capped, round-joined polyline of its width, emitted as
 *     one quad per segment plus a disc per vertex (all with the same winding
 *     as rect()/arc(), so overlapping pieces union under non-zero);
 *   - area: its rect, truncated to the top `areaFraction` (top-to-bottom wipe).
 */
export function traceRevealOp(sink: RevealPathSink, op: RevealOp, areaFraction = 1): void {
  if (op[0] === 'a') {
    const f = Math.min(1, Math.max(0, areaFraction));
    const h = (op[4] - op[2]) * f;
    if (h > 0 && op[3] > op[1]) sink.rect(op[1], op[2], op[3] - op[1], h);
    return;
  }

  const r = op[1] / 2;
  const n = (op.length - 2) >> 1;
  for (let i = 0; i < n; i++) {
    const x = op[2 + i * 2] as number;
    const y = op[3 + i * 2] as number;
    sink.moveTo(x + r, y);
    sink.arc(x, y, r, 0, Math.PI * 2);
    sink.closePath();
    if (i + 1 >= n) continue;
    const nx = op[4 + i * 2] as number;
    const ny = op[5 + i * 2] as number;
    const dx = nx - x;
    const dy = ny - y;
    const len = Math.hypot(dx, dy);
    if (len < 1e-6) continue;
    // Unit normal scaled to the radius; A -> D -> C -> B winds like rect().
    const ox = (-dy / len) * r;
    const oy = (dx / len) * r;
    sink.moveTo(x + ox, y + oy);
    sink.lineTo(x - ox, y - oy);
    sink.lineTo(nx - ox, ny - oy);
    sink.lineTo(nx + ox, ny + oy);
    sink.closePath();
  }
}

// ============================================================================
// Assets
// ============================================================================

export const PAINTING_FINAL_FILE = 'final.png';
export const PAINTING_MANIFEST_FILE = 'reveal.json';

/** Absolute (or API-relative) URL of a version asset. */
export function paintingAssetUrl(
  apiUrl: string,
  ref: Pick<PaintingVersionRef, 'asset_base'>,
  file: string
): string {
  const base = apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl;
  return `${base}${ref.asset_base}${file}`;
}
