/**
 * Program-painting reveal plan (docs/program-painting.md, "Client playback").
 *
 * The shared schedule (buildRevealSchedule) is flattened into plain number
 * arrays so it can be copied once to the UI runtime, where
 * `advanceRevealPlan` runs every frame. The cursor only moves forward, so
 * per-frame work is proportional to the ops revealed since the last frame.
 */

import type { RevealManifest, RevealPacing } from '@code-monet/shared';
import { DEFAULT_REVEAL_PACING, buildRevealSchedule } from '@code-monet/shared';

export const OP_STROKE = 0;
export const OP_AREA = 1;

export interface RevealPlanKeyframe {
  label: string;
  /** File name relative to the version's asset_base. */
  image: string;
  /** Global index of the keyframe's first op. */
  opStart: number;
  /** Global index one past the keyframe's last op. */
  opEnd: number;
  startMs: number;
  endMs: number;
}

/**
 * Flattened reveal manifest + schedule. Op `i` (global index across
 * keyframes) is `opKind[i]` with numbers `opData[opDataStart[i] .. opDataStart[i + 1])`:
 *   - stroke: width, x0, y0, x1, y1, ...
 *   - area:   x0, y0, x1, y1
 * Coordinates are manifest (image) pixels.
 */
export interface RevealPlan {
  width: number;
  height: number;
  totalMs: number;
  keyframes: RevealPlanKeyframe[];
  opKind: number[];
  opEndMs: number[];
  opDataStart: number[];
  opData: number[];
}

export function buildRevealPlan(
  manifest: RevealManifest,
  pacing: RevealPacing = DEFAULT_REVEAL_PACING
): RevealPlan {
  const schedule = buildRevealSchedule(manifest, pacing);
  const keyframes: RevealPlanKeyframe[] = [];
  const opKind: number[] = [];
  const opEndMs: number[] = [];
  const opDataStart: number[] = [];
  const opData: number[] = [];

  manifest.keyframes.forEach((kf, k) => {
    const sched = schedule.keyframes[k]!;
    const opStart = opKind.length;
    kf.ops.forEach((op, j) => {
      opKind.push(op[0] === 's' ? OP_STROKE : OP_AREA);
      opEndMs.push(sched.opEndMs[j]!);
      opDataStart.push(opData.length);
      for (let i = 1; i < op.length; i++) opData.push(op[i] as number);
    });
    keyframes.push({
      label: kf.label,
      image: kf.image,
      opStart,
      opEnd: opKind.length,
      startMs: sched.startMs,
      endMs: sched.endMs,
    });
  });
  opDataStart.push(opData.length);

  return {
    width: manifest.width,
    height: manifest.height,
    totalMs: schedule.totalMs,
    keyframes,
    opKind,
    opEndMs,
    opDataStart,
    opData,
  };
}

/** Playback position: keyframe being revealed and next unrevealed global op. */
export interface RevealCursor {
  kf: number;
  op: number;
}

/** Drawing operations requested by `advanceRevealPlan` (implemented per platform). */
export interface RevealSink {
  /** Reveal completed global ops [from, to) of keyframe `kf`. */
  revealOps(kf: number, from: number, to: number): void;
  /** Keyframe `kf` is complete: draw its image in full. */
  settleKeyframe(kf: number): void;
  /** Partially wipe (top to bottom) the in-flight area op `op` of keyframe `kf`. */
  wipeArea(kf: number, op: number, progress: number): void;
}

/**
 * Advance `cursor` (mutated) to the scheduled position at `elapsedMs`,
 * emitting only what changed since the previous call. Completed keyframes are
 * settled with a full draw so the next keyframe reveals over an exact
 * picture. Returns true when the version is fully revealed.
 */
export function advanceRevealPlan(
  plan: RevealPlan,
  cursor: RevealCursor,
  elapsedMs: number,
  sink: RevealSink
): boolean {
  'worklet';
  const nOps = plan.opEndMs.length;
  const kfs = plan.keyframes;
  const done = elapsedMs >= plan.totalMs;

  let target = cursor.op;
  if (done) {
    target = nOps;
  } else {
    while (target < nOps && plan.opEndMs[target]! <= elapsedMs) target++;
  }

  while (cursor.kf < kfs.length) {
    const kf = kfs[cursor.kf]!;
    const upto = Math.min(target, kf.opEnd);
    if (upto > cursor.op) {
      sink.revealOps(cursor.kf, cursor.op, upto);
      cursor.op = upto;
    }
    if (cursor.op < kf.opEnd) break;
    if (!done && elapsedMs < kf.endMs) break;
    sink.settleKeyframe(cursor.kf);
    cursor.kf += 1;
  }
  if (cursor.kf >= kfs.length) return true;

  const kf = kfs[cursor.kf]!;
  const op = cursor.op;
  if (op < kf.opEnd && plan.opKind[op] === OP_AREA) {
    const start = op > kf.opStart ? plan.opEndMs[op - 1]! : kf.startMs;
    const dur = plan.opEndMs[op]! - start;
    const progress = dur > 0 ? Math.min(1, Math.max(0, (elapsedMs - start) / dur)) : 0;
    if (progress > 0) sink.wipeArea(cursor.kf, op, progress);
  }
  return false;
}

/**
 * Absolute URL for an API-relative asset path (e.g. a gallery `image_url`).
 */
export function apiAssetUrl(apiUrl: string, path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  const base = apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl;
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}

/** Response of `GET /gallery/{n}/strokes` (fields the app uses for raster pieces). */
export interface GalleryStrokesFormat {
  /** 'raster' | 'strokes' (absent on older servers). */
  format?: string | null;
  image_url?: string | null;
}

/** Final image URL of a raster (program-painting) gallery piece, else null. */
export function galleryRasterImageUrl(apiUrl: string, data: GalleryStrokesFormat): string | null {
  if (data.format !== 'raster' || !data.image_url) return null;
  return apiAssetUrl(apiUrl, data.image_url);
}
