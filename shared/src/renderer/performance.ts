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

/** Largest picture or atlas a client decodes (as on iOS: RGBAPixels.maxPixelCount). */
export const PERFORMANCE_MAX_PIXELS = 4096 * 4096;

/**
 * A WebP image's size, read from its header without decoding it (null if the
 * bytes are not a WebP). The stream's images come from the painting program's
 * process, so their size is checked before anything is allocated for them.
 */
export function webpSize(bytes: Uint8Array): { width: number; height: number } | null {
  const tag = (o: number): string => String.fromCharCode(...bytes.subarray(o, o + 4));
  if (bytes.length < 30 || tag(0) !== 'RIFF' || tag(8) !== 'WEBP') return null;
  const u16 = (o: number): number => bytes[o]! | (bytes[o + 1]! << 8);
  const u24 = (o: number): number => u16(o) | (bytes[o + 2]! << 16);
  switch (tag(12)) {
    case 'VP8 ': // lossy: key frame header, then 14-bit width and height
      return { width: u16(26) & 0x3fff, height: u16(28) & 0x3fff };
    case 'VP8L': {
      // lossless: signature byte, then 14 bits each of width - 1 and height - 1
      const bits = bytes[21]! | (bytes[22]! << 8) | (bytes[23]! << 16) | (bytes[24]! << 24);
      return { width: (bits & 0x3fff) + 1, height: ((bits >>> 14) & 0x3fff) + 1 };
    }
    case 'VP8X': // extended: 24-bit canvas width - 1 and height - 1
      return { width: u24(24) + 1, height: u24(27) + 1 };
    default:
      return null;
  }
}

/**
 * Largest frame a stream may carry. The stream is written by the painting
 * program's process, so a frame may claim any length; one this large is an
 * error, not something to wait for.
 */
export const PERFORMANCE_MAX_FRAME_BYTES = 64 * 1024 * 1024;

/**
 * Incremental frame parser: push bytes as they arrive, take complete frames.
 * Arriving bytes are kept as chunks and joined only once a whole frame is
 * there, so work stays linear in the stream however it is split.
 */
export class PerformanceParser {
  private chunks: Uint8Array[] = [];
  private length = 0;

  push(bytes: Uint8Array): PerformanceFrame[] {
    if (bytes.length > 0) {
      this.chunks.push(bytes);
      this.length += bytes.length;
    }
    const frames: PerformanceFrame[] = [];
    for (;;) {
      const size = this.frameSize();
      if (size === null || this.length < size) break;
      frames.push(parseFrame(this.take(size)));
    }
    return frames;
  }

  /** Bytes in the next frame, once its four part lengths have arrived. */
  private frameSize(): number | null {
    let offset = 0;
    for (let k = 0; k < 4; k++) {
      if (this.length < offset + 4) return null;
      const n = this.u32(offset);
      offset += 4 + n;
      if (offset > PERFORMANCE_MAX_FRAME_BYTES) {
        throw new Error(`performance frame too large (${offset} bytes)`);
      }
    }
    return offset;
  }

  private u32(offset: number): number {
    const b = new Uint8Array(4);
    let i = 0;
    let base = 0;
    for (const chunk of this.chunks) {
      while (i < 4 && offset + i < base + chunk.length) {
        b[i] = chunk[offset + i - base]!;
        i++;
      }
      if (i === 4) break;
      base += chunk.length;
    }
    return new DataView(b.buffer).getUint32(0, true);
  }

  private take(size: number): Uint8Array {
    const out = new Uint8Array(size);
    let filled = 0;
    while (filled < size) {
      const chunk = this.chunks[0]!;
      const n = Math.min(chunk.length, size - filled);
      out.set(chunk.subarray(0, n), filled);
      filled += n;
      if (n === chunk.length) this.chunks.shift();
      else this.chunks[0] = chunk.subarray(n);
    }
    this.length -= size;
    return out;
  }
}

function parseFrame(frame: Uint8Array): PerformanceFrame {
  const view = new DataView(frame.buffer, frame.byteOffset, frame.byteLength);
  const parts: Uint8Array[] = [];
  let j = 0;
  for (let k = 0; k < 4; k++) {
    const n = view.getUint32(j, true);
    parts.push(frame.subarray(j + 4, j + 4 + n));
    j += 4 + n;
  }
  const meta = JSON.parse(new TextDecoder().decode(parts[0])) as PerformanceMeta;
  return { meta, index: parts[1]!, color: parts[2]!, order: parts[3]! };
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
