/**
 * Optimized in-progress stroke renderer for Skia.
 *
 * Uses a two-phase approach (same algorithm as SVG InProgressStroke):
 * 1. For the "tail" (last N points), compute freehand outline fresh each frame
 * 2. For the "body" (earlier points), cache the computed Skia path
 *
 * This dramatically reduces computation when animating long strokes since we
 * only recalculate the perfect-freehand outline for recent points.
 */

import React, { useMemo, useRef, useEffect, memo } from 'react';
import { Group, Path as SkiaPath, Skia, BlurMask } from '@shopify/react-native-skia';

import type { Point, StrokeStyle, BrushName, BrushPreset } from '@code-monet/shared';
import {
  getFreehandOutline,
  outlineToSvgPath,
  PAINTERLY_FREEHAND_OPTIONS,
  getBrushPreset,
  brushPresetToFreehandOptions,
  getBristleOutlines,
  applyVelocityPressure,
  type FreehandStrokeOptions,
} from '@code-monet/shared';

// How many points from the end to recompute each frame
const TAIL_LENGTH = 15;
// How many new points before we commit more to the cached body
const COMMIT_THRESHOLD = 20;

const DEFAULT_STROKE_COLOR = '#1a1a2e';

type SkiaPathType = NonNullable<ReturnType<typeof Skia.Path.MakeFromSVGString>>;

interface CachedBody {
  path: SkiaPathType | null;
  bristles: SkiaPathType[];
  committedLength: number;
}

interface SkiaInProgressStrokeProps {
  points: Point[];
  style: StrokeStyle;
  brushName?: BrushName;
  blur?: boolean;
}

/**
 * Compute body Skia path and bristles for caching.
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
  const svgD = outlineToSvgPath(bodyOutline);
  const path = svgD ? Skia.Path.MakeFromSVGString(svgD) : null;

  let bristles: SkiaPathType[] = [];
  if (brushPreset && brushPreset.bristleCount > 0 && newBodyPoints.length > 1) {
    const bristleOutlines = getBristleOutlines(
      newBodyPoints,
      brushPreset.bristleCount,
      brushPreset.bristleSpread * strokeWidth,
      options
    );
    bristles = bristleOutlines
      .map((o) => {
        const d = outlineToSvgPath(o);
        return d.length > 0 ? Skia.Path.MakeFromSVGString(d) : null;
      })
      .filter((p): p is SkiaPathType => p !== null);
  }

  return { path, bristles, committedLength: bodyEndIndex };
}

export const SkiaInProgressStroke = memo(function SkiaInProgressStroke({
  points,
  style,
  brushName,
  blur = false,
}: SkiaInProgressStrokeProps): React.ReactElement | null {
  const cachedBodyRef = useRef<CachedBody>({ path: null, bristles: [], committedLength: 0 });
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
      cachedBodyRef.current = { path: null, bristles: [], committedLength: 0 };
    }
    prevPointsLengthRef.current = points.length;
  }, [points.length]);

  // Update body cache when we have enough new points
  useEffect(() => {
    if (points.length === 0) return;

    const bodyEndIndex = Math.max(0, points.length - TAIL_LENGTH);
    const cached = cachedBodyRef.current;

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

  // Compute tail (always fresh)
  const { tailPath, tailBristles } = useMemo(() => {
    if (points.length === 0) {
      return { tailPath: null, tailBristles: [] };
    }

    const bodyEndIndex = Math.max(0, points.length - TAIL_LENGTH);

    // Overlap a few points with body for smooth visual join
    const overlapPoints = 3;
    const tailStartIndex = Math.max(0, bodyEndIndex - overlapPoints);
    const tailPoints = points.slice(tailStartIndex);

    if (tailPoints.length === 0) {
      return { tailPath: null, tailBristles: [] };
    }

    // Derive pressure from velocity
    const velocityOptions = applyVelocityPressure(tailPoints, options, strokeWidth);

    const tailOutline = getFreehandOutline(tailPoints, velocityOptions);
    const tailSvgD = outlineToSvgPath(tailOutline);
    const tailPath = tailSvgD ? Skia.Path.MakeFromSVGString(tailSvgD) : null;

    let tailBristles: SkiaPathType[] = [];
    if (brushPreset && brushPreset.bristleCount > 0 && tailPoints.length > 1) {
      const tailBristleCount = Math.min(brushPreset.bristleCount, 5);
      const bristleOutlines = getBristleOutlines(
        tailPoints,
        tailBristleCount,
        brushPreset.bristleSpread * strokeWidth,
        velocityOptions
      );
      tailBristles = bristleOutlines
        .map((o) => {
          const d = outlineToSvgPath(o);
          return d.length > 0 ? Skia.Path.MakeFromSVGString(d) : null;
        })
        .filter((p): p is SkiaPathType => p !== null);
    }

    return { tailPath, tailBristles };
  }, [points, options, brushPreset, strokeWidth]);

  // Read cached body
  const { path: bodyPath, bristles: bodyBristles } = cachedBodyRef.current;

  if (!tailPath && !bodyPath) return null;

  const mainOpacity = (brushPreset?.mainOpacity ?? 1) * strokeOpacity;
  const bristleOpacity = (brushPreset?.bristleOpacity ?? 0.3) * strokeOpacity;

  const content = (
    <>
      {/* Body bristle strokes (cached) */}
      {bodyBristles.map((p, i) => (
        <SkiaPath key={`body-bristle-${i}`} path={p} color={strokeColor} style="fill" opacity={bristleOpacity} />
      ))}

      {/* Committed body (cached) */}
      {bodyPath && (
        <SkiaPath path={bodyPath} color={strokeColor} style="fill" opacity={mainOpacity} />
      )}

      {/* Tail bristle strokes (fresh each frame) */}
      {tailBristles.map((p, i) => (
        <SkiaPath key={`tail-bristle-${i}`} path={p} color={strokeColor} style="fill" opacity={bristleOpacity} />
      ))}

      {/* Live tail (fresh each frame) */}
      {tailPath && (
        <SkiaPath path={tailPath} color={strokeColor} style="fill" opacity={mainOpacity} />
      )}
    </>
  );

  if (blur) {
    return (
      <Group>
        <BlurMask blur={1.5} style="normal" />
        {content}
      </Group>
    );
  }

  return <Group>{content}</Group>;
});
