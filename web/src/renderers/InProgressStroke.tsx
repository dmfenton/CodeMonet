/**
 * Optimized in-progress stroke renderer that avoids full recomputation.
 *
 * Uses a two-phase approach:
 * 1. For the "tail" (last N points), compute freehand outline fresh each frame
 * 2. For the "body" (earlier points), cache the computed SVG path
 *
 * This dramatically reduces computation when animating long strokes since we
 * only recalculate the perfect-freehand outline for recent points.
 */

import React, { useMemo, useRef, useEffect, memo } from 'react';

import type { Point, StrokeStyle, BrushName, BrushPreset } from '@code-monet/shared';
import {
  getFreehandOutline,
  outlineToSvgPath,
  PAINTERLY_FREEHAND_OPTIONS,
  getBrushPreset,
  brushPresetToFreehandOptions,
  getBristleOutlines,
  type FreehandStrokeOptions,
} from '@code-monet/shared';

// How many points from the end to recompute each frame
const TAIL_LENGTH = 15;
// How many new points before we commit more to the cached body
const COMMIT_THRESHOLD = 20;

const DEFAULT_STROKE_COLOR = '#1a1a2e';

interface CachedBody {
  path: string;
  bristles: string[];
  committedLength: number;
}

interface InProgressStrokeProps {
  points: Point[];
  style: StrokeStyle;
  brushName?: BrushName;
  blur?: boolean;
}

/**
 * Compute body path and bristles for caching.
 * Extracted as a pure function to avoid side effects during render.
 */
function computeBodyCache(
  points: Point[],
  bodyEndIndex: number,
  options: FreehandStrokeOptions,
  brushPreset: BrushPreset | null,
  strokeWidth: number
): CachedBody {
  const newBodyPoints = points.slice(0, bodyEndIndex);
  const bodyOutline = getFreehandOutline(newBodyPoints, options);
  const path = outlineToSvgPath(bodyOutline);

  let bristles: string[] = [];
  if (brushPreset && brushPreset.bristleCount > 0 && newBodyPoints.length > 1) {
    const bristleOutlines = getBristleOutlines(
      newBodyPoints,
      brushPreset.bristleCount,
      brushPreset.bristleSpread * strokeWidth,
      options
    );
    bristles = bristleOutlines.map((o) => outlineToSvgPath(o)).filter((d) => d.length > 0);
  }

  return { path, bristles, committedLength: bodyEndIndex };
}

export const InProgressStroke = memo(function InProgressStroke({
  points,
  style,
  brushName,
  blur = false,
}: InProgressStrokeProps): React.ReactElement | null {
  // Track committed body path - stored in ref for persistence across renders
  const cachedBodyRef = useRef<CachedBody>({ path: '', bristles: [], committedLength: 0 });
  // Track previous points length to detect stroke reset
  const prevPointsLengthRef = useRef<number>(0);

  const strokeWidth = style.stroke_width || 2.5;
  const strokeColor = style.color || DEFAULT_STROKE_COLOR;
  const strokeOpacity = style.opacity ?? 1;

  const brushPreset = useMemo(
    () => (brushName ? getBrushPreset(brushName) : null),
    [brushName]
  );

  const options = useMemo(
    () =>
      brushPreset
        ? brushPresetToFreehandOptions(brushPreset, strokeWidth)
        : { ...PAINTERLY_FREEHAND_OPTIONS, size: strokeWidth },
    [brushPreset, strokeWidth]
  );

  // Reset cache when stroke changes (points length decreases = new stroke)
  useEffect(() => {
    if (points.length < prevPointsLengthRef.current) {
      // New stroke started - reset cache
      cachedBodyRef.current = { path: '', bristles: [], committedLength: 0 };
    }
    prevPointsLengthRef.current = points.length;
  }, [points.length]);

  // Update body cache when we have enough new points
  // This runs as an effect to avoid side effects during render
  useEffect(() => {
    if (points.length === 0) return;

    const bodyEndIndex = Math.max(0, points.length - TAIL_LENGTH);
    const cached = cachedBodyRef.current;

    // Commit more to body if we have enough new points
    if (bodyEndIndex > cached.committedLength + COMMIT_THRESHOLD) {
      cachedBodyRef.current = computeBodyCache(
        points,
        bodyEndIndex,
        options,
        brushPreset,
        strokeWidth
      );
    }
  }, [points, options, brushPreset, strokeWidth]);

  // Compute tail (always fresh) - this is a pure calculation, safe in useMemo
  const { tailPath, tailBristles } = useMemo(() => {
    if (points.length === 0) {
      return { tailPath: '', tailBristles: [] };
    }

    const bodyEndIndex = Math.max(0, points.length - TAIL_LENGTH);

    // Overlap a few points with body for smooth visual join
    const overlapPoints = 3;
    const tailStartIndex = Math.max(0, bodyEndIndex - overlapPoints);
    const tailPoints = points.slice(tailStartIndex);

    if (tailPoints.length === 0) {
      return { tailPath: '', tailBristles: [] };
    }

    // Derive pressure factor from average inter-point spacing in the tail
    // Closer points = slower movement = more pressure = thicker stroke
    let velocityOptions = options;
    if (tailPoints.length > 1) {
      let totalTailDist = 0;
      for (let i = 1; i < tailPoints.length; i++) {
        const dx = tailPoints[i]!.x - tailPoints[i - 1]!.x;
        const dy = tailPoints[i]!.y - tailPoints[i - 1]!.y;
        totalTailDist += Math.sqrt(dx * dx + dy * dy);
      }
      const avgDist = totalTailDist / (tailPoints.length - 1);
      const pressureFactor = Math.max(0.6, Math.min(1.2, 1.0 / (1 + avgDist * 0.015)));
      velocityOptions = { ...options, size: (options.size ?? strokeWidth) * pressureFactor };
    }

    const tailOutline = getFreehandOutline(tailPoints, velocityOptions);
    const tailPath = outlineToSvgPath(tailOutline);

    let tailBristles: string[] = [];
    if (brushPreset && brushPreset.bristleCount > 0 && tailPoints.length > 1) {
      // Use fewer bristles for tail to maintain performance
      const tailBristleCount = Math.min(brushPreset.bristleCount, 5);
      const bristleOutlines = getBristleOutlines(
        tailPoints,
        tailBristleCount,
        brushPreset.bristleSpread * strokeWidth,
        velocityOptions
      );
      tailBristles = bristleOutlines.map((o) => outlineToSvgPath(o)).filter((d) => d.length > 0);
    }

    return { tailPath, tailBristles };
  }, [points, options, brushPreset, strokeWidth]);

  // Read cached body (computed in effect, read during render is safe)
  const { path: bodyPath, bristles: bodyBristles } = cachedBodyRef.current;

  if (!tailPath && !bodyPath) return null;

  const filterId = blur ? 'painterly-blur' : undefined;
  const mainOpacity = (brushPreset?.mainOpacity ?? 1) * strokeOpacity;
  const bristleOpacity = (brushPreset?.bristleOpacity ?? 0.3) * strokeOpacity;

  return (
    <g filter={filterId ? `url(#${filterId})` : undefined}>
      {/* Body bristle strokes (cached) */}
      {bodyBristles.map((d, i) => (
        <path key={`body-bristle-${i}`} d={d} fill={strokeColor} fillOpacity={bristleOpacity} />
      ))}

      {/* Committed body (cached) */}
      {bodyPath && <path d={bodyPath} fill={strokeColor} fillOpacity={mainOpacity} />}

      {/* Tail bristle strokes (fresh each frame) */}
      {tailBristles.map((d, i) => (
        <path key={`tail-bristle-${i}`} d={d} fill={strokeColor} fillOpacity={bristleOpacity} />
      ))}

      {/* Live tail (fresh each frame) */}
      {tailPath && <path d={tailPath} fill={strokeColor} fillOpacity={mainOpacity} />}
    </g>
  );
});
