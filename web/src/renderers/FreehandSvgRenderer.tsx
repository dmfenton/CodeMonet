/**
 * SVG renderer with perfect-freehand for natural strokes (web version).
 *
 * This renderer uses perfect-freehand to generate natural-looking
 * stroke outlines, then renders them as filled SVG paths.
 */

import React, { useMemo, memo } from 'react';

import type { Point, RendererProps, StrokeStyle, BrushName, Path, DrawingStyleConfig } from '@code-monet/shared';
import {
  getEffectiveAgentStrokeStyle,
  getEffectiveStyle,
  getFreehandOutline,
  outlineToSvgPath,
  PAINTERLY_FREEHAND_OPTIONS,
  getBristleOutlines,
  getBrushPreset,
  brushPresetToFreehandOptions,
  pathToSvgD,
  samplePathPoints,
} from '@code-monet/shared';

import { IdleParticles } from '../components/IdleParticles';
import { InProgressStroke } from './InProgressStroke';

/**
 * Default fallback color for strokes (forest ink).
 * Used as safety fallback if style.color is somehow missing.
 */
const DEFAULT_STROKE_COLOR = '#1f4d34';

/**
 * Render a stroke with perfect-freehand outline.
 */
function FreehandStroke({
  points,
  style,
  brushName,
  blur = false,
}: {
  points: Point[];
  style: StrokeStyle;
  brushName?: BrushName;
  blur?: boolean;
}): React.ReactElement | null {
  // Extract style values with explicit fallbacks for safety
  // This ensures strokes are always visible even if style is incomplete
  const strokeColor = style.color || DEFAULT_STROKE_COLOR;
  const strokeWidth = style.stroke_width || 2.5;
  const strokeOpacity = style.opacity ?? 1;

  const { mainPath, bristlePaths, brush } = useMemo(() => {
    if (points.length === 0) return { mainPath: '', bristlePaths: [], brush: null };

    // Get brush preset if specified
    const brushPreset = brushName ? getBrushPreset(brushName) : null;
    const options = brushPreset
      ? brushPresetToFreehandOptions(brushPreset, strokeWidth)
      : { ...PAINTERLY_FREEHAND_OPTIONS, size: strokeWidth };

    // Main stroke outline
    const outline = getFreehandOutline(points, options);
    const main = outlineToSvgPath(outline);

    // Bristle strokes for texture
    let bristles: string[] = [];
    if (brushPreset && brushPreset.bristleCount > 0) {
      const bristleOutlines = getBristleOutlines(
        points,
        brushPreset.bristleCount,
        brushPreset.bristleSpread * strokeWidth,
        options
      );
      bristles = bristleOutlines.map((o) => outlineToSvgPath(o)).filter((d) => d.length > 0);
    }

    return { mainPath: main, bristlePaths: bristles, brush: brushPreset };
  }, [points, strokeWidth, brushName]);

  if (!mainPath) return null;

  const filterId = blur ? 'painterly-blur' : undefined;

  return (
    <g filter={filterId ? `url(#${filterId})` : undefined}>
      {/* Bristle strokes (background texture) */}
      {bristlePaths.map((d, i) => (
        <path
          key={`bristle-${i}`}
          d={d}
          fill={strokeColor}
          fillOpacity={(brush?.bristleOpacity ?? 0.3) * strokeOpacity}
        />
      ))}

      {/* Main stroke */}
      <path
        d={mainPath}
        fill={strokeColor}
        fillOpacity={(brush?.mainOpacity ?? 1) * strokeOpacity}
      />
    </g>
  );
}

/**
 * Render a single-point stroke as a filled circle.
 */
function StrokeDot({ point, style }: { point: Point; style: StrokeStyle }): React.ReactElement {
  // Explicit fallbacks to ensure visibility
  const color = style.color || DEFAULT_STROKE_COLOR;
  const opacity = style.opacity ?? 1;
  const radius = Math.max((style.stroke_width || 2.5) / 2, 1.5);
  return <circle cx={point.x} cy={point.y} r={radius} fill={color} fillOpacity={opacity} />;
}

/**
 * Memoized completed stroke renderer.
 *
 * This component takes the raw stroke (Path) object and handles all the
 * expensive computation internally with proper memoization. The stroke object
 * reference is stable (doesn't change once added), so React.memo prevents
 * re-renders and the internal useMemo prevents recomputation.
 *
 * Previously, samplePathPoints was called in the parent's map() loop,
 * creating new arrays every render that defeated FreehandStroke's useMemo.
 */
interface MemoizedStrokeProps {
  stroke: Path;
  styleConfig: DrawingStyleConfig;
  isPaintMode: boolean;
}

const MemoizedStroke = memo(function MemoizedStroke({
  stroke,
  styleConfig,
  isPaintMode,
}: MemoizedStrokeProps): React.ReactElement | null {
  const style = useMemo(
    () => getEffectiveStyle(stroke, styleConfig),
    [stroke, styleConfig]
  );

  // Sample points from the path - must be called unconditionally (Rules of Hooks)
  // For SVG type strokes, this returns an empty array which is fine
  const points = useMemo(() => samplePathPoints(stroke), [stroke]);

  // Handle SVG path type strokes (use raw d string, not sampled points)
  if (stroke.type === 'svg') {
    const d = pathToSvgD(stroke, isPaintMode);
    if (!d) return null;
    const filterId = isPaintMode ? 'painterly-blur' : undefined;
    return (
      <path
        d={d}
        stroke={style.color}
        strokeWidth={style.stroke_width}
        fill="none"
        strokeLinecap={style.stroke_linecap}
        strokeLinejoin={style.stroke_linejoin}
        opacity={style.opacity}
        filter={filterId ? `url(#${filterId})` : undefined}
      />
    );
  }

  if (points.length === 0) return null;

  // Single point = dot
  if (points.length === 1 && points[0]) {
    return <StrokeDot point={points[0]} style={style} />;
  }

  return (
    <FreehandStroke
      points={points}
      style={style}
      brushName={isPaintMode ? stroke.brush : undefined}
      blur={isPaintMode}
    />
  );
});

/**
 * Pen position indicator with outer ring and inner dot.
 */
function PenIndicator({
  position,
  penDown,
  color,
}: {
  position: Point;
  penDown: boolean;
  color: string;
}): React.ReactElement {
  const outerRadius = penDown ? 6 : 8;
  const innerRadius = penDown ? 3 : 4;

  return (
    <g>
      <circle
        cx={position.x}
        cy={position.y}
        r={outerRadius}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeOpacity={0.6}
      />
      <circle cx={position.x} cy={position.y} r={innerRadius} fill={color} fillOpacity={0.8} />
    </g>
  );
}

/**
 * FreehandSvgRenderer - SVG renderer with perfect-freehand strokes (web version).
 *
 * Provides painterly effects without requiring Skia/canvaskit:
 * - Natural pressure-sensitive stroke outlines
 * - Bristle texture simulation
 * - SVG blur filter for soft edges
 */

/**
 * Memoized layer for all completed strokes.
 * Only re-renders when the strokes array reference changes (on STROKE_COMPLETE),
 * not on every STROKE_PROGRESS_BATCH dispatch during animation.
 */
interface CompletedStrokesLayerProps {
  strokes: readonly Path[];
  styleConfig: DrawingStyleConfig;
  isPaintMode: boolean;
}

const CompletedStrokesLayer = memo(function CompletedStrokesLayer({
  strokes,
  styleConfig,
  isPaintMode,
}: CompletedStrokesLayerProps): React.ReactElement {
  return (
    <>
      {strokes.map((stroke, index) => (
        <MemoizedStroke
          key={index}
          stroke={stroke}
          styleConfig={styleConfig}
          isPaintMode={isPaintMode}
        />
      ))}
    </>
  );
});

export function FreehandSvgRenderer({
  strokes,
  currentStroke,
  agentStroke,
  agentStrokeStyle,
  penPosition,
  penDown,
  styleConfig,
  showIdleAnimation,
  primaryColor,
}: RendererProps): React.ReactElement {
  const isPaintMode = styleConfig.type === 'paint';

  return (
    <>
      {/* Define blur filter for painterly effect */}
      <defs>
        <filter id="painterly-blur" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="1.5" />
        </filter>
      </defs>

      {/* Idle animation particles */}
      <IdleParticles visible={showIdleAnimation} />

      {/* Completed strokes - memoized layer skips re-render during animation */}
      <CompletedStrokesLayer strokes={strokes} styleConfig={styleConfig} isPaintMode={isPaintMode} />

      {/* Current human stroke */}
      {currentStroke.length > 0 &&
        (currentStroke.length === 1 ? (
          <StrokeDot point={currentStroke[0]!} style={styleConfig.human_stroke} />
        ) : (
          <FreehandStroke
            points={currentStroke}
            style={styleConfig.human_stroke}
            blur={isPaintMode}
          />
        ))}

      {/* Agent in-progress stroke - using optimized incremental renderer */}
      {agentStroke.length > 0 &&
        ((): React.ReactElement => {
          const style = getEffectiveAgentStrokeStyle(styleConfig, agentStrokeStyle);
          return agentStroke.length === 1 ? (
            <StrokeDot point={agentStroke[0]!} style={style} />
          ) : (
            <InProgressStroke points={agentStroke} style={style} blur={isPaintMode} />
          );
        })()}

      {/* Pen position indicator */}
      {penPosition && <PenIndicator position={penPosition} penDown={penDown} color={primaryColor} />}
    </>
  );
}
