/**
 * Raster layer for program painting (paint mode).
 *
 * Shows the base image (previous version's final.png, or blank) and, while a
 * version is playing, reveals its keyframe images over the current picture
 * along the recorded brush footprints (docs/program-painting.md). Drawing is
 * incremental: each animation frame clips to only the newly revealed ops.
 */

import React, { useEffect, useRef } from 'react';
import type {
  PaintingVersionRef,
  RevealManifest,
  RevealOp,
  RevealPacing,
  RevealSchedule,
} from '@code-monet/shared';
import {
  PAINTING_FINAL_FILE,
  PAINTING_MANIFEST_FILE,
  buildRevealSchedule,
  paintingAssetUrl,
  revealOpBounds,
  revealProgressAt,
  traceRevealOp,
} from '@code-monet/shared';
import { loadRevealManifest } from './revealManifest';

/** Backing-store pixels per logical canvas unit. */
const RASTER_SCALE = 2;

/** Soft leading edge of an area wipe, as a fraction of the rect height. */
const WIPE_FEATHER = 0.06;

export interface RevealPlaybackInfo {
  /** Version being revealed (null when idle). */
  version: number | null;
  keyframe: number;
  label: string;
  opsDone: number;
  playing: boolean;
}

interface RasterRevealLayerProps {
  apiUrl: string;
  base: PaintingVersionRef | null;
  playing: PaintingVersionRef | null;
  width: number;
  height: number;
  /** Called once a playing version is fully revealed (final.png drawn). */
  onPlaybackDone?: (assetBase: string) => void;
  /** Called every animation frame while playing, and once when idle. */
  onProgress?: (info: RevealPlaybackInfo) => void;
  /** Playback pacing (default: live pacing from docs/program-painting.md). */
  pacing?: RevealPacing;
}

const imageCache = new Map<string, Promise<HTMLImageElement>>();

function loadImage(url: string): Promise<HTMLImageElement> {
  const cached = imageCache.get(url);
  if (cached) return cached;
  const promise = new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.decoding = 'async';
    img.onload = (): void => resolve(img);
    img.onerror = (): void => reject(new Error(`Failed to load ${url}`));
    img.src = url;
  });
  // Don't cache failures; a later attempt may succeed.
  promise.catch(() => imageCache.delete(url));
  imageCache.set(url, promise);
  // Bound the cache: versions are immutable but superseded quickly.
  if (imageCache.size > 48) {
    const oldest = imageCache.keys().next().value;
    if (oldest !== undefined) imageCache.delete(oldest);
  }
  return promise;
}

/** Draw the whole image over the canvas. */
function drawFull(ctx: CanvasRenderingContext2D, img: HTMLImageElement): void {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1;
  ctx.drawImage(img, 0, 0, ctx.canvas.width, ctx.canvas.height);
}

interface Bounds {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/**
 * Copy `img` into the canvas through `clip` (manifest coordinates),
 * restricted to `bounds` so the per-frame cost scales with what changed.
 */
function revealThrough(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  manifest: RevealManifest,
  clip: Path2D,
  bounds: Bounds,
  alpha = 1
): void {
  const x0 = Math.max(0, Math.floor(bounds.x0));
  const y0 = Math.max(0, Math.floor(bounds.y0));
  const x1 = Math.min(manifest.width, Math.ceil(bounds.x1));
  const y1 = Math.min(manifest.height, Math.ceil(bounds.y1));
  if (x1 <= x0 || y1 <= y0) return;

  const sx = ctx.canvas.width / manifest.width;
  const sy = ctx.canvas.height / manifest.height;
  const ix = img.naturalWidth / manifest.width;
  const iy = img.naturalHeight / manifest.height;

  ctx.save();
  ctx.setTransform(sx, 0, 0, sy, 0, 0);
  ctx.globalAlpha = alpha;
  ctx.clip(clip);
  ctx.drawImage(img, x0 * ix, y0 * iy, (x1 - x0) * ix, (y1 - y0) * iy, x0, y0, x1 - x0, y1 - y0);
  ctx.restore();
}

/** Reveal ops [from, to) of a keyframe in one clipped draw. */
function revealOps(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  manifest: RevealManifest,
  ops: readonly RevealOp[],
  from: number,
  to: number
): void {
  if (to <= from) return;
  const clip = new Path2D();
  const bounds: Bounds = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  for (let i = from; i < to; i++) {
    const op = ops[i]!;
    traceRevealOp(clip, op);
    const b = revealOpBounds(op);
    bounds.x0 = Math.min(bounds.x0, b.x0);
    bounds.y0 = Math.min(bounds.y0, b.y0);
    bounds.x1 = Math.max(bounds.x1, b.x1);
    bounds.y1 = Math.max(bounds.y1, b.y1);
  }
  revealThrough(ctx, img, manifest, clip, bounds);
}

/** Partial top-to-bottom wipe of an area op, with a soft leading edge. */
function revealAreaWipe(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  manifest: RevealManifest,
  op: RevealOp,
  progress: number
): void {
  if (op[0] !== 'a') return;
  const [, x0, y0, x1, y1] = op;
  const h = y1 - y0;
  const edge = y0 + h * progress;
  const solid = new Path2D();
  solid.rect(x0, y0, x1 - x0, edge - y0);
  revealThrough(ctx, img, manifest, solid, { x0, y0, x1, y1: edge });

  // Feather: a translucent band below the edge; later frames overwrite it opaquely.
  const featherH = Math.min(h * WIPE_FEATHER, y1 - edge);
  if (featherH > 0) {
    const band = new Path2D();
    band.rect(x0, edge, x1 - x0, featherH);
    revealThrough(ctx, img, manifest, band, { x0, y0: edge, x1, y1: edge + featherH }, 0.35);
  }
}

interface Cursor {
  keyframe: number;
  opsDone: number;
}

/**
 * Advance the canvas from `cursor` to the scheduled progress at `elapsedMs`.
 * Completed keyframes are settled with a full draw of their image so the next
 * keyframe reveals over an exact picture. Returns true when the version is done.
 */
function advanceReveal(
  ctx: CanvasRenderingContext2D,
  manifest: RevealManifest,
  schedule: RevealSchedule,
  images: readonly HTMLImageElement[],
  cursor: Cursor,
  elapsedMs: number
): boolean {
  const progress = revealProgressAt(schedule, elapsedMs);
  const targetKf = progress.phase === 'done' ? manifest.keyframes.length : progress.keyframe;

  while (cursor.keyframe < targetKf) {
    const kf = manifest.keyframes[cursor.keyframe]!;
    const img = images[cursor.keyframe]!;
    revealOps(ctx, img, manifest, kf.ops, cursor.opsDone, kf.ops.length);
    drawFull(ctx, img);
    cursor.keyframe += 1;
    cursor.opsDone = 0;
  }
  if (progress.phase === 'done') return true;

  const kf = manifest.keyframes[cursor.keyframe]!;
  const img = images[cursor.keyframe]!;
  revealOps(ctx, img, manifest, kf.ops, cursor.opsDone, progress.opsDone);
  cursor.opsDone = progress.opsDone;

  const active = progress.active;
  if (active) {
    const op = kf.ops[active.index];
    if (op && op[0] === 'a') revealAreaWipe(ctx, img, manifest, op, active.progress);
  }
  return false;
}

export function RasterRevealLayer({
  apiUrl,
  base,
  playing,
  width,
  height,
  onPlaybackDone,
  onProgress,
  pacing,
}: RasterRevealLayerProps): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  /** asset_base whose final image the canvas currently shows in full ('' = blank). */
  const shownRef = useRef<string | null>(null);
  const callbacksRef = useRef({ onPlaybackDone, onProgress });
  callbacksRef.current = { onPlaybackDone, onProgress };
  // Read when a version starts playing; changing it doesn't restart playback.
  const pacingRef = useRef(pacing);
  pacingRef.current = pacing;
  // Versions are immutable per asset_base; the effect is keyed by it.
  const playingRef = useRef(playing);
  playingRef.current = playing;

  const baseKey = base?.asset_base ?? '';
  const playingKey = playing?.asset_base ?? '';
  const backingW = Math.round(width * RASTER_SCALE);
  const backingH = Math.round(height * RASTER_SCALE);

  // Resizing the backing store clears it; force the base to redraw.
  // (Declared before the draw effect so it runs first.)
  useEffect(() => {
    shownRef.current = null;
  }, [backingW, backingH]);

  useEffect(() => {
    const playing = playingKey ? playingRef.current : null;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    let cancelled = false;
    let raf = 0;
    const report = (info: RevealPlaybackInfo): void => callbacksRef.current.onProgress?.(info);
    const idle = (): void =>
      report({ version: null, keyframe: -1, label: '', opsDone: 0, playing: false });

    const showBase = async (): Promise<void> => {
      if (shownRef.current === baseKey) return;
      if (!baseKey) {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        shownRef.current = '';
        return;
      }
      const img = await loadImage(
        paintingAssetUrl(apiUrl, { asset_base: baseKey }, PAINTING_FINAL_FILE)
      );
      if (cancelled) return;
      drawFull(ctx, img);
      shownRef.current = baseKey;
    };

    const play = async (ref: PaintingVersionRef): Promise<void> => {
      const url = (file: string): string => paintingAssetUrl(apiUrl, ref, file);
      const manifest = await loadRevealManifest(url(PAINTING_MANIFEST_FILE));
      const images = await Promise.all(manifest.keyframes.map((kf) => loadImage(url(kf.image))));
      // Warm the final image while animating
      const finalImage = loadImage(url(PAINTING_FINAL_FILE));
      if (cancelled) return;

      const schedule = buildRevealSchedule(manifest, pacingRef.current);
      const cursor: Cursor = { keyframe: 0, opsDone: 0 };
      shownRef.current = null; // canvas is mid-reveal
      const start = performance.now();

      await new Promise<void>((resolve) => {
        const frame = (now: number): void => {
          if (cancelled) return resolve();
          const done = advanceReveal(ctx, manifest, schedule, images, cursor, now - start);
          if (done) return resolve();
          report({
            version: ref.version,
            keyframe: cursor.keyframe,
            label: manifest.keyframes[cursor.keyframe]?.label ?? '',
            opsDone: cursor.opsDone,
            playing: true,
          });
          raf = requestAnimationFrame(frame);
        };
        raf = requestAnimationFrame(frame);
      });
      if (cancelled) return;

      drawFull(ctx, await finalImage);
      if (cancelled) return;
      shownRef.current = ref.asset_base;
      idle();
      callbacksRef.current.onPlaybackDone?.(ref.asset_base);
    };

    const run = async (): Promise<void> => {
      try {
        await showBase();
      } catch (error) {
        console.warn('[RasterRevealLayer] base image failed:', error);
      }
      if (cancelled) return;
      if (!playing) {
        idle();
        return;
      }
      try {
        await play(playing);
      } catch (error) {
        if (cancelled) return;
        // Can't animate: show the final directly and move on.
        console.warn('[RasterRevealLayer] reveal failed, showing final:', error);
        try {
          drawFull(ctx, await loadImage(paintingAssetUrl(apiUrl, playing, PAINTING_FINAL_FILE)));
          shownRef.current = playing.asset_base;
        } catch (finalError) {
          console.warn('[RasterRevealLayer] final image failed:', finalError);
        }
        if (cancelled) return;
        idle();
        callbacksRef.current.onPlaybackDone?.(playing.asset_base);
      }
    };

    void run();
    return (): void => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [apiUrl, baseKey, playingKey, backingW, backingH]);

  return (
    <canvas
      ref={canvasRef}
      data-testid="raster-reveal-layer"
      width={backingW}
      height={backingH}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
      }}
    />
  );
}
