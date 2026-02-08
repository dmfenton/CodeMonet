/**
 * SVG-based canvas renderer for web.
 * Uses native browser SVG elements for all stroke rendering.
 *
 * This is the "blue" renderer in the blue-green deployment.
 * The "green" renderer will be SkiaRenderer (using canvaskit-wasm).
 */

import React, { memo, useMemo } from 'react';

import type { Path, DrawingStyleConfig, RendererProps } from '@code-monet/shared';
import {
  createTaperedStrokePath,
  getEffectiveStyle,
  pathToSvgD,
  pointsToSvgD,
  useSettlingStrokes,
  SETTLE_OPACITY,
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
      <circle
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
    <path
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
}: RendererProps): React.ReactElement {
  const settlingIndices = useSettlingStrokes(strokes.length);

  return (
    <>
      {/* Idle animation - floating particles when canvas is empty and agent is idle */}
      <IdleParticles visible={showIdleAnimation} />

      {/* Completed strokes - using MemoizedStroke to prevent recalculation */}
      {strokes.map((stroke, index) => (
        <g key={index} opacity={settlingIndices.has(index) ? SETTLE_OPACITY : 1}>
          <MemoizedStroke
            stroke={stroke}
            styleConfig={styleConfig}
            index={index}
          />
        </g>
      ))}

      {/* Current stroke in progress (human drawing) */}
      {currentStroke.length > 0 &&
        (currentStroke.length === 1 ? (
          <circle
            cx={currentStroke[0]!.x}
            cy={currentStroke[0]!.y}
            r={Math.max(1, styleConfig.human_stroke.stroke_width / 2)}
            fill={styleConfig.human_stroke.color}
            opacity={styleConfig.human_stroke.opacity}
          />
        ) : styleConfig.type === 'paint' && currentStroke.length > 3 ? (
          // Paint mode: tapered brush stroke
          <path
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
          <path
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
          // Get effective style - use agentStrokeStyle overrides in paint mode
          const effectiveColor =
            styleConfig.supports_color && agentStrokeStyle?.color
              ? agentStrokeStyle.color
              : styleConfig.agent_stroke.color;
          const effectiveWidth =
            styleConfig.supports_variable_width && agentStrokeStyle?.stroke_width
              ? agentStrokeStyle.stroke_width
              : styleConfig.agent_stroke.stroke_width;
          const effectiveOpacity =
            styleConfig.supports_opacity && agentStrokeStyle?.opacity !== undefined
              ? agentStrokeStyle.opacity
              : styleConfig.agent_stroke.opacity;

          if (agentStroke.length === 1) {
            return (
              <circle
                cx={agentStroke[0]!.x}
                cy={agentStroke[0]!.y}
                r={Math.max(1, effectiveWidth / 2)}
                fill={effectiveColor}
                opacity={effectiveOpacity}
              />
            );
          }

          return styleConfig.type === 'paint' && agentStroke.length > 3 ? (
            // Paint mode: tapered brush stroke with smooth curves
            <path
              d={createTaperedStrokePath(agentStroke, effectiveWidth * 1.5, 0.7)}
              fill={effectiveColor}
              opacity={effectiveOpacity * 0.9}
            />
          ) : (
            // Plotter mode: smooth bezier polyline for organic feel
            <path
              d={pointsToSvgD(agentStroke, true)}
              stroke={effectiveColor}
              strokeWidth={effectiveWidth}
              fill="none"
              strokeLinecap={styleConfig.agent_stroke.stroke_linecap}
              strokeLinejoin={styleConfig.agent_stroke.stroke_linejoin}
            />
          );
        })()}

      {/* Pen position indicator */}
      {penPosition && (
        <>
          {/* Outer ring */}
          <circle
            cx={penPosition.x}
            cy={penPosition.y}
            r={penDown ? 12 : 16}
            fill="none"
            stroke={primaryColor}
            strokeWidth={2}
            opacity={0.5}
          />
          {/* Inner dot */}
          <circle
            cx={penPosition.x}
            cy={penPosition.y}
            r={penDown ? 6 : 4}
            fill={penDown ? primaryColor : 'none'}
            stroke={primaryColor}
            strokeWidth={2}
          />
        </>
      )}
    </>
  );
}
