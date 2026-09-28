/**
 * The performance stream (server/code_monet/paintlib/performance.py): the
 * pixels each paint op changed, in paint order, with one-hand timing.
 * Platform-independent parsing and scheduling; platforms decode the atlases
 * and paste pixels.
 *
 *   frame := part(json) part(index) part(color) part(order);  part := u32 len | bytes
 */

export type PerformanceMeta =
  | {
      kind: 'header';
      width: number;
      height: number;
      format: number;
      /** 'previous': a revision, performed over the last version's final picture. */
      base?: 'blank' | 'previous';
    }
  | { kind: 'chunk'; stage: string; atlas: [number, number]; patches: number }
  | { kind: 'end'; ms: number }
  | { kind: 'error' };

export interface PerformanceFrame {
  meta: PerformanceMeta;
  index: Uint8Array;
  color: Uint8Array;
  order: Uint8Array;
}

/** One patch: pixels of one op, pasted into the picture over [t, t + dur]. */
export interface PerformancePatch {
  t: number;
  dur: number;
  /** Top-left in the color atlas (px); order atlas is at 1/ORDER_SCALE. */
  ax: number;
  ay: number;
  w: number;
  h: number;
  /** Top-left in the picture (px). */
  x: number;
  y: number;
}

/** A version's performance stream, next to its other assets. */
export const PERFORMANCE_FILE = 'performance.bin';
/** A version's finished picture (exact; the stream is lossy). */
export const PAINTING_FINAL_FILE = 'final.png';

/** Absolute (or API-relative) URL of a version asset. */
export function paintingAssetUrl(
  apiUrl: string,
  ref: { asset_base: string },
  file: string
): string {
  const base = apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl;
  return `${base}${ref.asset_base}${file}`;
}

/** The order atlas is this many times smaller than the color atlas. */
export const PERFORMANCE_ORDER_SCALE = 4;
const INDEX_BYTES = 20;

/**
 * Incremental frame parser: push bytes as they arrive, take complete frames.
 */
export class PerformanceParser {
  private buf = new Uint8Array(0);

  push(bytes: Uint8Array): PerformanceFrame[] {
    const merged = new Uint8Array(this.buf.length + bytes.length);
    merged.set(this.buf);
    merged.set(bytes, this.buf.length);
    this.buf = merged;
    const frames: PerformanceFrame[] = [];
    const view = new DataView(merged.buffer, merged.byteOffset, merged.byteLength);
    let i = 0;
    for (;;) {
      const parts: Uint8Array[] = [];
      let j = i;
      for (let k = 0; k < 4; k++) {
        if (j + 4 > merged.length) break;
        const n = view.getUint32(j, true);
        if (j + 4 + n > merged.length) break;
        parts.push(merged.subarray(j + 4, j + 4 + n));
        j += 4 + n;
      }
      if (parts.length < 4) break;
      const meta = JSON.parse(new TextDecoder().decode(parts[0])) as PerformanceMeta;
      frames.push({ meta, index: parts[1]!, color: parts[2]!, order: parts[3]! });
      i = j;
    }
    this.buf = merged.slice(i);
    return frames;
  }
}

export function decodePatchIndex(index: Uint8Array): PerformancePatch[] {
  const view = new DataView(index.buffer, index.byteOffset, index.byteLength);
  const out: PerformancePatch[] = [];
  for (let o = 0; o + INDEX_BYTES <= index.length; o += INDEX_BYTES) {
    out.push({
      t: view.getFloat32(o, true),
      dur: view.getFloat32(o + 4, true),
      ax: view.getUint16(o + 8, true),
      ay: view.getUint16(o + 10, true),
      w: view.getUint16(o + 12, true),
      h: view.getUint16(o + 14, true),
      x: view.getUint16(o + 16, true),
      y: view.getUint16(o + 18, true),
    });
  }
  return out;
}

/**
 * Whether a patch lies inside the picture and its atlases. The stream is the
 * painting program's output (untrusted): patches that don't fit are skipped.
 */
export function patchFits(
  p: PerformancePatch,
  picture: { width: number; height: number },
  color: { width: number; height: number },
  order: { width: number; height: number }
): boolean {
  const k = PERFORMANCE_ORDER_SCALE;
  return (
    p.w > 0 &&
    p.h > 0 &&
    Number.isFinite(p.t) &&
    Number.isFinite(p.dur) &&
    p.x + p.w <= picture.width &&
    p.y + p.h <= picture.height &&
    p.ax + p.w <= color.width &&
    p.ay + p.h <= color.height &&
    Math.ceil((p.ax + p.w) / k) <= order.width &&
    Math.ceil((p.ay + p.h) / k) <= order.height
  );
}

/**
 * Order threshold (1..255) revealed `now` ms into a patch: pixels whose order
 * value is <= this are painted. Order 0 (nothing changed there) lands at the end.
 */
export function patchOrderThreshold(patch: PerformancePatch, now: number): number {
  if (now >= patch.t + patch.dur) return 256;
  if (now < patch.t) return 0;
  const p = patch.dur > 0 ? (now - patch.t) / patch.dur : 1;
  return 1 + p * 254;
}

/** A live performance never lags what has arrived by more than this much video time. */
export const PERFORMANCE_MAX_BEHIND_MS = 60_000;

/**
 * Each stroke is on screen at least this long (wall time) unless catching up,
 * so a sparse painting's strokes are seen landing one by one.
 */
export const PERFORMANCE_MIN_STROKE_MS = 400;

/**
 * Playback rate (hand ms per ms). Normally the base rate, but a stroke in
 * flight (`activeDurMs` of hand time) is slowed to take at least
 * `minStrokeMs` on screen; and playback speeds up whenever the received-but-
 * unplayed hand time (`backlogMs`) would take longer than `maxBehindMs`
 * (catching up wins). Dense paintings are always catching up, so their time
 * stays proportional to their strokes' hand time; sparse ones play stroke by
 * stroke.
 */
export function playbackRate(
  baseRate: number,
  backlogMs: number,
  maxBehindMs: number = PERFORMANCE_MAX_BEHIND_MS,
  activeDurMs: number | null = null,
  minStrokeMs: number = PERFORMANCE_MIN_STROKE_MS
): number {
  const catchUp = backlogMs / maxBehindMs;
  const legible = activeDurMs !== null && activeDurMs > 0 ? activeDurMs / minStrokeMs : Infinity;
  return Math.max(catchUp, Math.min(baseRate, legible));
}
