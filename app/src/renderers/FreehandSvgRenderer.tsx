/**
 * SVG renderer with perfect-freehand for natural strokes.
 *
 * This renderer uses perfect-freehand to generate natural-looking
 * stroke outlines, then renders them as filled SVG paths.
 * Works without Skia, providing painterly effects via SVG.
 */

import React, { useMemo, memo } from 'react';
import { StyleSheet } from 'react-native';
import Svg, { Circle, Defs, G, Path as SvgPath, Filter, FeGaussianBlur } from 'react-native-svg';

import type { Point, RendererProps, StrokeStyle, BrushName, Path, DrawingStyleConfig } from '@code-monet/shared';
import {
  CANVAS_HEIGHT,
  CANVAS_WIDTH,
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
  useSettlingStrokes,
  SETTLE_OPACITY,
} from '@code-monet/shared';

import { IdleParticles } from '../components/IdleParticles';
import { InProgressStroke } from './InProgressStroke';

/**
 * Default fallback color for strokes (dark blue-black).
 * Used as safety fallback if style.color is somehow missing.
 */
const DEFAULT_STROKE_COLOR = '#1a1a2e';

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
    <G filter={filterId ? `url(#${filterId})` : undefined}>
      {/* Bristle strokes (background texture) */}
      {bristlePaths.map((d, i) => (
        <SvgPath
          key={`bristle-${i}`}
          d={d}
          fill={strokeColor}
          fillOpacity={(brush?.bristleOpacity ?? 0.3) * strokeOpacity}
        />
      ))}

      {/* Main stroke */}
      <SvgPath
        d={mainPath}
        fill={strokeColor}
        fillOpacity={(brush?.mainOpacity ?? 1) * strokeOpacity}
      />
    </G>
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
  return <Circle cx={point.x} cy={point.y} r={radius} fill={color} fillOpacity={opacity} />;
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
      <SvgPath
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
    <G>
      <Circle
        cx={position.x}
        cy={position.y}
        r={outerRadius}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeOpacity={0.6}
      />
      <Circle cx={position.x} cy={position.y} r={innerRadius} fill={color} fillOpacity={0.8} />
    </G>
  );
}

/**
 * FreehandSvgRenderer - SVG renderer with perfect-freehand strokes.
 *
 * Provides painterly effects without requiring Skia:
 * - Natural pressure-sensitive stroke outlines
 * - Bristle texture simulation
 * - SVG blur filter for soft edges
 * - Stroke settling effect (new strokes fade in)
 */
export function FreehandSvgRenderer({
  strokes,
  currentStroke,
  agentStroke,
  agentStrokeStyle,
  penPosition,
  penDown,
  styleConfig,
  showIdleAnimation,
  // width and height come from props but we use CANVAS_WIDTH/HEIGHT constants
  width: _width,
  height: _height,
  primaryColor,
}: RendererProps): React.ReactElement {
  void _width;
  void _height;
  const isPaintMode = styleConfig.type === 'paint';
  const settlingIndices = useSettlingStrokes(strokes.length);

  return (
    <Svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
      style={styles.svg}
    >
      {/* Define blur filter for painterly effect */}
      <Defs>
        <Filter id="painterly-blur" x="-20%" y="-20%" width="140%" height="140%">
          <FeGaussianBlur stdDeviation="1.5" />
        </Filter>
      </Defs>

      {/* Idle animation particles */}
      <IdleParticles visible={showIdleAnimation} />

      {/* Completed strokes - using MemoizedStroke to prevent re-computation */}
      {strokes.map((stroke, index) => (
        <G key={index} opacity={settlingIndices.has(index) ? SETTLE_OPACITY : 1}>
          <MemoizedStroke
            stroke={stroke}
            styleConfig={styleConfig}
            isPaintMode={isPaintMode}
          />
        </G>
      ))}

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
        (() => {
          const style = getEffectiveAgentStrokeStyle(styleConfig, agentStrokeStyle);
          return agentStroke.length === 1 ? (
            <StrokeDot point={agentStroke[0]!} style={style} />
          ) : (
            <InProgressStroke points={agentStroke} style={style} blur={isPaintMode} />
          );
        })()}

      {/* Pen position indicator */}
      {penPosition && <PenIndicator position={penPosition} penDown={penDown} color={primaryColor} />}
    </Svg>
  );
}

const styles = StyleSheet.create({
  svg: {
    flex: 1,
  },
});
