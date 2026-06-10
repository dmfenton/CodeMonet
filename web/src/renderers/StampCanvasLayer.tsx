/**
 * Raster underlay that renders completed strokes with the stamp-based
 * painterly model (shared port of the server's painting.py renderer).
 *
 * Completed strokes are stamped incrementally as they arrive; in-progress
 * strokes stay in the SVG overlay and "settle" into paint on completion.
 */

import React, { useEffect, useRef } from 'react';
import type { DrawingStyleConfig, Path } from '@code-monet/shared';
import {
  computeStrokeStamps,
  getEffectiveStyle,
  pathToSvgD,
  samplePathPoints,
} from '@code-monet/shared';

import { drawStampsToContext } from './stampSprites';

/** Supersampling factor for the raster layer (canvas units → device pixels). */
const RASTER_SCALE = 2;

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
  drawStampsToContext(ctx, stamps, stroke.brush, stamps.length);
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
    // Assumes the reducer only appends strokes or replaces the whole array
    // (a replace produces a new strokes[0] reference). In-place edits of
    // existing strokes would require a full-repaint signal here.
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
