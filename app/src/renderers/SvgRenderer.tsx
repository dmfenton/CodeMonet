/**
 * SVG-based canvas renderer for React Native.
 * Uses react-native-svg for all stroke rendering.
 *
 * This is the "blue" renderer in the blue-green deployment.
 * The "green" renderer will be SkiaRenderer.
 */

import React, { memo, useMemo } from 'react';
import Svg, { Circle, Path as SvgPath } from 'react-native-svg';

import type { Path, DrawingStyleConfig, RendererProps } from '@code-monet/shared';
import {
  CANVAS_HEIGHT,
  CANVAS_WIDTH,
  createTaperedStrokePath,
  getEffectiveAgentStrokeStyle,
  getEffectiveStyle,
  pathToSvgD,
  pointsToSvgD,
} from '@code-monet/shared';

import { IdleParticles } from '../components/IdleParticles';

/**
 * Memoized stroke renderer for completed strokes.
 * Prevents recalculating style and path on every parent render.
 */
interface MemoizedStrokeProps {
  stroke: Path;
  styleConfig: DrawingStyleConfig;
  index: number;
}

const MemoizedStroke = memo(function MemoizedStroke({
  stroke,
  styleConfig,
  index,
}: MemoizedStrokeProps): React.ReactElement {
  const effectiveStyle = useMemo(
    () => getEffectiveStyle(stroke, styleConfig),
    [stroke, styleConfig]
  );
  const isPaintMode = styleConfig.type === 'paint';

  if (stroke.type !== 'svg' && stroke.points.length === 1) {
    const pt = stroke.points[0]!;
    const radius = Math.max(1, effectiveStyle.stroke_width / 2);
    return (
      <Circle
        key={`stroke-dot-${index}`}
        cx={pt.x}
        cy={pt.y}
        r={radius}
        fill={effectiveStyle.color}
        opacity={effectiveStyle.opacity}
      />
    );
  }

  return (
    <SvgPath
      key={`stroke-${index}`}
      d={pathToSvgD(stroke, isPaintMode)}
      stroke={effectiveStyle.color}
      strokeWidth={effectiveStyle.stroke_width}
      fill="none"
      strokeLinecap={effectiveStyle.stroke_linecap}
      strokeLinejoin={effectiveStyle.stroke_linejoin}
      opacity={effectiveStyle.opacity}
    />
  );
});

/**
 * Memoized layer for all completed strokes.
 * Only re-renders when the strokes array reference changes (on STROKE_COMPLETE),
 * not on every STROKE_PROGRESS_BATCH dispatch during animation.
 */
interface CompletedStrokesLayerProps {
  strokes: readonly Path[];
  styleConfig: DrawingStyleConfig;
}

const CompletedStrokesLayer = memo(function CompletedStrokesLayer({
  strokes,
  styleConfig,
}: CompletedStrokesLayerProps): React.ReactElement {
  return (
    <>
      {strokes.map((stroke, index) => (
        <MemoizedStroke
          key={index}
          stroke={stroke}
          styleConfig={styleConfig}
          index={index}
        />
      ))}
    </>
  );
});

export function SvgRenderer({
  strokes,
  currentStroke,
  agentStroke,
  agentStrokeStyle,
  penPosition,
  penDown,
  styleConfig,
  showIdleAnimation,
  primaryColor,
}: RendererProps): React.JSX.Element {
  return (
    <Svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Idle animation - floating particles when canvas is empty and agent is idle */}
      <IdleParticles visible={showIdleAnimation} />

      {/* Completed strokes - memoized layer skips re-render during animation */}
      <CompletedStrokesLayer strokes={strokes} styleConfig={styleConfig} />

      {/* Current stroke in progress (human drawing) */}
      {currentStroke.length > 0 &&
        (currentStroke.length === 1 ? (
          <Circle
            cx={currentStroke[0]!.x}
            cy={currentStroke[0]!.y}
            r={Math.max(1, styleConfig.human_stroke.stroke_width / 2)}
            fill={styleConfig.human_stroke.color}
            opacity={styleConfig.human_stroke.opacity}
          />
        ) : styleConfig.type === 'paint' && currentStroke.length > 3 ? (
          // Paint mode: tapered brush stroke
          <SvgPath
            d={createTaperedStrokePath(
              currentStroke,
              styleConfig.human_stroke.stroke_width * 1.5,
              0.7
            )}
            fill={styleConfig.human_stroke.color}
            opacity={styleConfig.human_stroke.opacity * 0.9}
          />
        ) : (
          // Plotter mode: simple polyline
          <SvgPath
            d={pointsToSvgD(currentStroke)}
            stroke={styleConfig.human_stroke.color}
            strokeWidth={styleConfig.human_stroke.stroke_width}
            fill="none"
            strokeLinecap={styleConfig.human_stroke.stroke_linecap}
            strokeLinejoin={styleConfig.human_stroke.stroke_linejoin}
          />
        ))}

      {/* Agent's in-progress stroke */}
      {agentStroke.length > 0 &&
        (() => {
          const style = getEffectiveAgentStrokeStyle(styleConfig, agentStrokeStyle);

          if (agentStroke.length === 1) {
            return (
              <Circle
                cx={agentStroke[0]!.x}
                cy={agentStroke[0]!.y}
                r={Math.max(1, style.stroke_width / 2)}
                fill={style.color}
                opacity={style.opacity}
              />
            );
          }

          return styleConfig.type === 'paint' && agentStroke.length > 3 ? (
            // Paint mode: tapered brush stroke
            <SvgPath
              d={createTaperedStrokePath(agentStroke, style.stroke_width * 1.5, 0.7)}
              fill={style.color}
              opacity={style.opacity * 0.9}
            />
          ) : (
            // Plotter mode: smooth bezier polyline for organic feel
            <SvgPath
              d={pointsToSvgD(agentStroke, true)}
              stroke={style.color}
              strokeWidth={style.stroke_width}
              fill="none"
              strokeLinecap={style.stroke_linecap}
              strokeLinejoin={style.stroke_linejoin}
            />
          );
        })()}

      {/* Pen position indicator - larger and more visible */}
      {penPosition && (
        <>
          {/* Outer ring */}
          <Circle
            cx={penPosition.x}
            cy={penPosition.y}
            r={penDown ? 12 : 16}
            fill="none"
            stroke={primaryColor}
            strokeWidth={2}
            opacity={0.5}
          />
          {/* Inner dot */}
          <Circle
            cx={penPosition.x}
            cy={penPosition.y}
            r={penDown ? 6 : 4}
            fill={penDown ? primaryColor : 'none'}
            stroke={primaryColor}
            strokeWidth={2}
          />
        </>
      )}
    </Svg>
  );
}
