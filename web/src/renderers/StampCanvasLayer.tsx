/**
 * Raster underlay that renders completed strokes with the stamp-based
 * painterly model (shared port of the server's painting.py renderer).
 *
 * Completed strokes are stamped incrementally as they arrive; in-progress
 * strokes stay in the SVG overlay and "settle" into paint on completion.
 */

import React, { useEffect, useRef } from 'react';
import type { BrushName, DrawingStyleConfig, Path } from '@code-monet/shared';
import {
  SPRITE_VARIANTS,
  computeStrokeStamps,
  generateSpriteAlpha,
  getEffectiveStyle,
  pathToSvgD,
  samplePathPoints,
} from '@code-monet/shared';

/** Supersampling factor for the raster layer (canvas units → device pixels). */
const RASTER_SCALE = 2;
const SPRITE_CACHE_MAX = 768;

type SpriteKey = string;

const tintedSpriteCache = new Map<SpriteKey, HTMLCanvasElement>();

function getTintedSprite(
  brush: BrushName | undefined,
  variant: number,
  r: number,
  g: number,
  b: number
): HTMLCanvasElement {
  // Quantize tint so nearby jittered colors share cache entries.
  const qr = r & 0xf8;
  const qg = g & 0xf8;
  const qb = b & 0xf8;
  const key = `${brush ?? 'default'}:${variant}:${qr},${qg},${qb}`;
  const cached = tintedSpriteCache.get(key);
  if (cached) return cached;

  const sprite = generateSpriteAlpha(brush, variant % SPRITE_VARIANTS);
  const canvas = document.createElement('canvas');
  canvas.width = sprite.width;
  canvas.height = sprite.height;
  const ctx = canvas.getContext('2d')!;
  const imageData = ctx.createImageData(sprite.width, sprite.height);
  const pixels = imageData.data;
  for (let i = 0; i < sprite.data.length; i++) {
    const a = sprite.data[i]!;
    const o = i * 4;
    pixels[o] = qr;
    pixels[o + 1] = qg;
    pixels[o + 2] = qb;
    pixels[o + 3] = Math.round(a * 255);
  }
  ctx.putImageData(imageData, 0, 0);

  if (tintedSpriteCache.size >= SPRITE_CACHE_MAX) {
    // Drop the oldest entries (Map preserves insertion order).
    const firstKey = tintedSpriteCache.keys().next().value;
    if (firstKey !== undefined) tintedSpriteCache.delete(firstKey);
  }
  tintedSpriteCache.set(key, canvas);
  return canvas;
}

function paintStroke(
  ctx: CanvasRenderingContext2D,
  stroke: Path,
  styleConfig: DrawingStyleConfig
): void {
  const style = getEffectiveStyle(stroke, styleConfig);

  // Fill pass (closed shapes: grounds, silhouettes, value masses)
  if (stroke.fill) {
    const d = stroke.type === 'svg' && stroke.d ? stroke.d : pathToSvgD(stroke, true);
    if (d) {
      ctx.save();
      ctx.globalAlpha = stroke.fill_opacity ?? style.opacity;
      ctx.fillStyle = stroke.fill;
      ctx.fill(new Path2D(d));
      ctx.restore();
    }
  }

  if (style.stroke_width <= 0) return;

  if (stroke.type === 'svg') {
    // SVG strokes are not point-sampled on the client; stroke directly.
    if (!stroke.d) return;
    ctx.save();
    ctx.globalAlpha = style.opacity;
    ctx.strokeStyle = style.color;
    ctx.lineWidth = style.stroke_width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke(new Path2D(stroke.d));
    ctx.restore();
    return;
  }

  const points = samplePathPoints(stroke);
  if (points.length < 2) return;

  const stamps = computeStrokeStamps(
    points,
    { color: style.color, strokeWidth: style.stroke_width, opacity: style.opacity },
    stroke.brush
  );
  for (const stamp of stamps) {
    const sprite = getTintedSprite(
      stroke.brush,
      stamp.variant,
      stamp.color.r,
      stamp.color.g,
      stamp.color.b
    );
    ctx.save();
    ctx.globalAlpha = stamp.alpha;
    ctx.translate(stamp.x, stamp.y);
    ctx.rotate(stamp.angle);
    ctx.drawImage(sprite, -stamp.length / 2, -stamp.width / 2, stamp.length, stamp.width);
    ctx.restore();
  }
}

interface StampCanvasLayerProps {
  strokes: readonly Path[];
  styleConfig: DrawingStyleConfig;
  width: number;
  height: number;
}

export function StampCanvasLayer({
  strokes,
  styleConfig,
  width,
  height,
}: StampCanvasLayerProps): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paintedRef = useRef<{ count: number; first: Path | null; styleType: string }>({
    count: 0,
    first: null,
    styleType: styleConfig.type,
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const painted = paintedRef.current;
    const sameSession =
      strokes.length >= painted.count &&
      (painted.count === 0 || strokes[0] === painted.first) &&
      painted.styleType === styleConfig.type;

    let from = painted.count;
    if (!sameSession) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      from = 0;
    }

    ctx.setTransform(RASTER_SCALE, 0, 0, RASTER_SCALE, 0, 0);
    for (let i = from; i < strokes.length; i++) {
      paintStroke(ctx, strokes[i]!, styleConfig);
    }

    paintedRef.current = {
      count: strokes.length,
      first: strokes.length > 0 ? strokes[0]! : null,
      styleType: styleConfig.type,
    };
  }, [strokes, styleConfig]);

  return (
    <canvas
      ref={canvasRef}
      width={width * RASTER_SCALE}
      height={height * RASTER_SCALE}
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
