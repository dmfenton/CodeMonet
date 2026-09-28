/**
 * Plays a performance stream (shared/src/renderer/performance.ts): fetches
 * performance.bin as it is written, and pastes each patch's pixels into the
 * picture in draw order at hand time x speed. The canvas backing store is the
 * picture itself (image px); nothing is re-rendered, only pixels copied.
 */

import React, { useEffect, useRef } from 'react';
import type { PerformancePatch } from '@code-monet/shared';
import {
  PERFORMANCE_MAX_PIXELS,
  PERFORMANCE_ORDER_SCALE,
  PerformanceParser,
  decodePatchIndex,
  patchFits,
  PERFORMANCE_MAX_BEHIND_MS,
  patchOrderThreshold,
  playbackRate,
  webpSize,
} from '@code-monet/shared';

export interface PerformanceProgress {
  stage: string;
  handMs: number;
  /** Hand time of the whole performance, once its end frame has arrived. */
  totalMs: number | null;
  playing: boolean;
}

interface PerformancePlayerProps {
  /** URL of performance.bin (may still be growing). */
  src: string;
  /** Picture before the performance (previous version's final), or blank. */
  baseSrc?: string | null;
  /** Hand-time multiplier for a painting performed from blank; may change while playing. */
  speed: number;
  /** Multiplier for a revision (a stream whose base is the previous version): small
   * changes, so played slower. Defaults to `speed`. */
  revisionSpeed?: number;
  /** Never lag what has arrived by more than this much playback time. */
  maxBehindMs?: number;
  onProgress?: (p: PerformanceProgress) => void;
  onDone?: () => void;
}

interface Chunk {
  stage: string;
  color: Uint8ClampedArray;
  colorW: number;
  order: Uint8ClampedArray;
  orderW: number;
  /** Decoded pixels held (color + order); released once every patch has played. */
  pixels: number;
  /** Patches of this chunk not yet played in full. */
  unplayed: number;
}

/**
 * Decoded-but-unplayed pixels the player holds before it stops reading ahead.
 * A big painting decodes to hundreds of megapixels; playback needs only what
 * is about to play.
 */
const DECODE_AHEAD_PIXELS = 24_000_000;
const EMPTY = new Uint8ClampedArray(0);

interface Entry {
  patch: PerformancePatch;
  chunk: Chunk;
}

/** The stream's images come from the painting program: size them before decoding. */
function checkSize(width: number, height: number): void {
  if (!(width > 0 && height > 0 && width * height <= PERFORMANCE_MAX_PIXELS)) {
    throw new Error(`performance image ${width}x${height} is too large`);
  }
}

async function decodePixels(
  bytes: Uint8Array
): Promise<{ data: Uint8ClampedArray; w: number; h: number }> {
  const size = webpSize(bytes);
  if (!size) throw new Error('performance atlas is not a WebP image');
  checkSize(size.width, size.height);
  const bmp = await createImageBitmap(new Blob([bytes as BlobPart], { type: 'image/webp' }));
  const c = document.createElement('canvas');
  c.width = bmp.width;
  c.height = bmp.height;
  const ctx = c.getContext('2d', { willReadFrequently: true })!;
  ctx.drawImage(bmp, 0, 0);
  bmp.close();
  return { data: ctx.getImageData(0, 0, c.width, c.height).data, w: c.width, h: c.height };
}

async function loadImage(src: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.decoding = 'async';
  img.src = src;
  await img.decode();
  return img;
}

/** Copy a patch's pixels whose draw order is <= threshold into the picture. */
function paste(pic: ImageData, e: Entry, threshold: number): void {
  const { patch: p, chunk: c } = e;
  const k = PERFORMANCE_ORDER_SCALE;
  const out = pic.data;
  const W = pic.width;
  const full = threshold >= 256;
  for (let yy = 0; yy < p.h; yy++) {
    const py = p.y + yy;
    if (py >= pic.height) break;
    const src = ((p.ay + yy) * c.colorW + p.ax) * 4;
    const dst = (py * W + p.x) * 4;
    if (full) {
      out.set(c.color.subarray(src, src + p.w * 4), dst);
      continue;
    }
    const orow = (((p.ay + yy) / k) | 0) * c.orderW;
    for (let xx = 0; xx < p.w; xx++) {
      const o = c.order[(orow + (((p.ax + xx) / k) | 0)) * 4]!;
      if ((o === 0 ? 255 : o) > threshold) continue;
      const s = src + xx * 4;
      const d = dst + xx * 4;
      out[d] = c.color[s]!;
      out[d + 1] = c.color[s + 1]!;
      out[d + 2] = c.color[s + 2]!;
      out[d + 3] = 255;
    }
  }
}

export function PerformancePlayer({
  src,
  baseSrc,
  speed,
  revisionSpeed,
  maxBehindMs = PERFORMANCE_MAX_BEHIND_MS,
  onProgress,
  onDone,
}: PerformancePlayerProps): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const speedRef = useRef({ speed, revisionSpeed, maxBehindMs });
  speedRef.current = { speed, revisionSpeed, maxBehindMs };
  const cbRef = useRef({ onProgress, onDone });
  cbRef.current = { onProgress, onDone };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let cancelled = false;
    // Aborting ends the download too (not just its reading) when we unmount.
    const abort = new AbortController();
    let raf = 0;
    const entries: Entry[] = [];
    let endMs: number | null = null;
    const lastPatchEnd = (): number => {
      const last = entries[entries.length - 1];
      return last ? last.patch.t + last.patch.dur : 0;
    };
    let revision = false;
    // Backpressure: ingest waits while too many decoded pixels are unplayed.
    let heldPixels = 0;
    let wakeIngest: (() => void) | null = null;
    const played = (e: Entry): void => {
      const c = e.chunk;
      c.unplayed -= 1;
      if (c.unplayed > 0) return;
      heldPixels -= c.pixels;
      c.color = EMPTY;
      c.order = EMPTY;
      c.pixels = 0;
      wakeIngest?.();
    };
    const room = async (): Promise<void> => {
      while (heldPixels > DECODE_AHEAD_PIXELS && !cancelled) {
        await new Promise<void>((resolve) => (wakeIngest = resolve));
        wakeIngest = null;
      }
    };
    let pic: ImageData | null = null;
    let ctx: CanvasRenderingContext2D | null = null;

    const start = async (width: number, height: number): Promise<void> => {
      checkSize(width, height);
      canvas.width = width;
      canvas.height = height;
      ctx = canvas.getContext('2d', { willReadFrequently: true });
      if (!ctx) return;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);
      // Only a revision paints over the previous picture; a first version starts blank.
      if (baseSrc && revision) {
        try {
          ctx.drawImage(await loadImage(baseSrc), 0, 0, width, height);
        } catch (error) {
          console.warn('[PerformancePlayer] base image failed:', error);
        }
      }
      pic = ctx.getImageData(0, 0, width, height);
    };

    // Stream in: frames are decoded strictly in order.
    const ingest = async (): Promise<void> => {
      const res = await fetch(src, { signal: abort.signal });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status} for ${src}`);
      const reader = res.body.getReader();
      const parser = new PerformanceParser();
      for (;;) {
        const { value, done } = await reader.read();
        if (cancelled) return;
        if (value) {
          for (const f of parser.push(value)) {
            if (f.meta.kind === 'header') {
              revision = f.meta.base === 'previous';
              await start(f.meta.width, f.meta.height);
            } else if (f.meta.kind === 'chunk') {
              await room();
              if (cancelled) return;
              const [color, order] = await Promise.all([
                decodePixels(f.color),
                decodePixels(f.order),
              ]);
              const chunk: Chunk = {
                stage: f.meta.stage,
                color: color.data,
                colorW: color.w,
                order: order.data,
                orderW: order.w,
                pixels: color.w * color.h + order.w * order.h,
                unplayed: 0,
              };
              const picture = { width: pic?.width ?? 0, height: pic?.height ?? 0 };
              const colorSize = { width: color.w, height: color.h };
              const orderSize = { width: order.w, height: order.h };
              for (const patch of decodePatchIndex(f.index)) {
                if (patchFits(patch, picture, colorSize, orderSize)) {
                  entries.push({ patch, chunk });
                  chunk.unplayed += 1;
                }
              }
              if (chunk.unplayed > 0) heldPixels += chunk.pixels;
            } else if (f.meta.kind === 'end') endMs = f.meta.ms;
            else endMs = lastPatchEnd(); // error frame: the run failed, stop here
          }
        }
        if (done) break;
      }
      if (endMs === null) endMs = lastPatchEnd();
    };

    let now = 0;
    let last = performance.now();
    let cursor = 0;
    const frame = (wall: number): void => {
      if (cancelled) return;
      const dt = wall - last;
      last = wall;
      if (pic && ctx) {
        // Never play past what has arrived (a live stream may be behind).
        const lastEntry = entries[entries.length - 1];
        const horizon = endMs ?? (lastEntry ? lastEntry.patch.t + lastEntry.patch.dur : 0);
        const { speed: s, revisionSpeed: rs, maxBehindMs: behind } = speedRef.current;
        const base = Math.max(0, revision && rs !== undefined ? rs : s);
        // The stroke in flight (if any) is played legibly unless catching up.
        const flight = entries[cursor];
        const activeDur = flight && flight.patch.t <= now ? flight.patch.dur : null;
        const rate = playbackRate(base, horizon - now, behind, activeDur);
        now = Math.min(now + dt * rate, horizon);
        let x0 = Infinity;
        let y0 = Infinity;
        let x1 = -Infinity;
        let y1 = -Infinity;
        for (let i = cursor; i < entries.length && entries[i]!.patch.t <= now; i++) {
          const e = entries[i]!;
          const thr = patchOrderThreshold(e.patch, now);
          paste(pic, e, thr);
          x0 = Math.min(x0, e.patch.x);
          y0 = Math.min(y0, e.patch.y);
          x1 = Math.max(x1, e.patch.x + e.patch.w);
          y1 = Math.max(y1, e.patch.y + e.patch.h);
          if (thr >= 256 && i === cursor) played(entries[cursor++]!);
        }
        const ended = endMs !== null && now >= endMs;
        if (ended) {
          // The end: whatever is left lands in full (float rounding can leave
          // the last patch a hair short of its end time).
          for (; cursor < entries.length; cursor++) {
            const e = entries[cursor]!;
            paste(pic, e, 256);
            played(e);
            x0 = Math.min(x0, e.patch.x);
            y0 = Math.min(y0, e.patch.y);
            x1 = Math.max(x1, e.patch.x + e.patch.w);
            y1 = Math.max(y1, e.patch.y + e.patch.h);
          }
        }
        if (x1 > x0) ctx.putImageData(pic, 0, 0, x0, y0, x1 - x0, y1 - y0);
        const active = entries[Math.min(cursor, entries.length - 1)];
        cbRef.current.onProgress?.({
          stage: active?.chunk.stage ?? '',
          handMs: now,
          totalMs: endMs,
          playing: true,
        });
        if (ended) {
          cbRef.current.onProgress?.({ stage: '', handMs: now, totalMs: endMs, playing: false });
          cbRef.current.onDone?.();
          return;
        }
      }
      raf = requestAnimationFrame(frame);
    };

    ingest().catch((error: unknown) => {
      if (cancelled) return; // unmounted: the abort is ours
      // No stream (a version from before performances) or it broke off: end
      // here, so the caller settles on the version's final picture.
      console.warn('[PerformancePlayer] stream failed:', error);
      cancelled = true;
      cancelAnimationFrame(raf);
      cbRef.current.onProgress?.({ stage: '', handMs: now, totalMs: null, playing: false });
      cbRef.current.onDone?.();
    });
    raf = requestAnimationFrame(frame);
    return (): void => {
      cancelled = true;
      wakeIngest?.();
      abort.abort();
      cancelAnimationFrame(raf);
    };
  }, [src, baseSrc]);

  return (
    <canvas
      ref={canvasRef}
      data-testid="performance-player"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
    />
  );
}
