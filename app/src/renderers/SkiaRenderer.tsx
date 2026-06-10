/**
 * Skia-based canvas renderer for React Native.
 *
 * Uses @shopify/react-native-skia for GPU-accelerated rendering
 * with support for blur, blend modes, and custom shaders.
 *
 * This renderer handles all stroke types:
 * - Freehand/painterly: perfect-freehand outlines with bristle texture
 * - SVG paths: raw SVG d-string rendering (for bezier/arc strokes)
 * - Plotter mode: simple stroked paths (not filled outlines)
 */

import React, { useCallback, useMemo, memo, useState } from 'react';
import { LayoutChangeEvent, StyleSheet, View } from 'react-native';
import {
  Canvas,
  Path as SkiaPath,
  Group,
  Circle,
  Skia,
  BlurMask,
  fitbox,
  rect,
} from '@shopify/react-native-skia';

import type { Path, Point, RendererProps, StrokeStyle, BrushName, DrawingStyleConfig } from '@code-monet/shared';
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

import { SkiaIdleParticles } from '../components/SkiaIdleParticles';
import { SkiaInProgressStroke } from './SkiaInProgressStroke';
import { SkiaStampedStroke } from './SkiaStampedStroke';

const DEFAULT_STROKE_COLOR = '#1a1a2e';

/**
 * Render a freehand stroke with painterly effects using Skia paths.
 */
function PainterlyStroke({
  points,
  style,
  brushName,
  blur = 0,
}: {
  points: Point[];
  style: StrokeStyle;
  brushName?: BrushName;
  blur?: number;
}): React.ReactElement | null {
  const strokeColor = style.color || DEFAULT_STROKE_COLOR;
  const strokeWidth = style.stroke_width || 2.5;
  const strokeOpacity = style.opacity ?? 1;

  const { path, bristlePaths, brush } = useMemo(() => {
    if (points.length === 0) return { path: null, bristlePaths: [], brush: null };

    const brushPreset = brushName ? getBrushPreset(brushName) : null;
    const options = brushPreset
      ? brushPresetToFreehandOptions(brushPreset, strokeWidth)
      : { ...PAINTERLY_FREEHAND_OPTIONS, size: strokeWidth };

    const outline = getFreehandOutline(points, options);
    const mainPath = outline.length > 0 ? Skia.Path.MakeFromSVGString(outlineToSvgPath(outline)) : null;

    let bristles: NonNullable<ReturnType<typeof Skia.Path.MakeFromSVGString>>[] = [];
    if (brushPreset && brushPreset.bristleCount > 0) {
      const bristleOutlines = getBristleOutlines(
        points,
        brushPreset.bristleCount,
        brushPreset.bristleSpread * strokeWidth,
        options
      );
      bristles = bristleOutlines
        .map((o) => (o.length > 0 ? Skia.Path.MakeFromSVGString(outlineToSvgPath(o)) : null))
        .filter((p): p is NonNullable<typeof p> => p !== null);
    }

    return { path: mainPath, bristlePaths: bristles, brush: brushPreset };
  }, [points, strokeWidth, brushName]);

  if (!path) return null;

  const mainOpacity = (brush?.mainOpacity ?? 1) * strokeOpacity;
  const bristleOpacity = (brush?.bristleOpacity ?? 0.3) * strokeOpacity;

  return (
    <Group>
      {bristlePaths.map((bristlePath, i) => (
        <SkiaPath
          key={`bristle-${i}`}
          path={bristlePath}
          color={strokeColor}
          style="fill"
          opacity={bristleOpacity}
        />
      ))}

      {blur > 0 ? (
        <Group>
          <BlurMask blur={blur} style="normal" />
          <SkiaPath path={path} color={strokeColor} style="fill" opacity={mainOpacity} />
        </Group>
      ) : (
        <SkiaPath path={path} color={strokeColor} style="fill" opacity={mainOpacity} />
      )}
    </Group>
  );
}

/**
 * Render a single-point stroke as a dot.
 */
function StrokeDot({ point, style }: { point: Point; style: StrokeStyle }): React.ReactElement {
  const color = style.color || DEFAULT_STROKE_COLOR;
  const opacity = style.opacity ?? 1;
  const radius = Math.max((style.stroke_width || 2.5) / 2, 1.5);
  return <Circle cx={point.x} cy={point.y} r={radius} color={color} opacity={opacity} />;
}

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
    <Group>
      <Circle
        cx={position.x}
        cy={position.y}
        r={outerRadius}
        color={color}
        style="stroke"
        strokeWidth={1.5}
        opacity={0.6}
      />
      <Circle cx={position.x} cy={position.y} r={innerRadius} color={color} opacity={0.8} />
    </Group>
  );
}

/**
 * Memoized completed stroke renderer.
 * Handles all stroke types: freehand (point-sampled), SVG (d-string), plotter.
 */
interface MemoizedSkiaStrokeProps {
  stroke: Path;
  styleConfig: DrawingStyleConfig;
  isPaintMode: boolean;
}

const MemoizedSkiaStroke = memo(function MemoizedSkiaStroke({
  stroke,
  styleConfig,
  isPaintMode,
}: MemoizedSkiaStrokeProps): React.ReactElement | null {
  const style = useMemo(
    () => getEffectiveStyle(stroke, styleConfig),
    [stroke, styleConfig]
  );

  const points = useMemo(() => samplePathPoints(stroke), [stroke]);

  // SVG-type strokes: render from raw d-string, preserving filled forms.
  if (stroke.type === 'svg') {
    const d = pathToSvgD(stroke, isPaintMode);
    if (!d) return null;

    const skiaPath = Skia.Path.MakeFromSVGString(d);
    if (!skiaPath) return null;

    const strokeColor = style.color || DEFAULT_STROKE_COLOR;
    const strokeOpacity = style.opacity ?? 1;
    const fillColor = stroke.fill;
    const fillOpacity = fillColor ? (stroke.fill_opacity ?? strokeOpacity) : undefined;
    const shouldStroke = style.stroke_width > 0;

    return (
      <Group>
        {fillColor && (
          <SkiaPath path={skiaPath} color={fillColor} style="fill" opacity={fillOpacity} />
        )}
        {shouldStroke &&
          (isPaintMode ? (
            <Group>
              <BlurMask blur={1.5} style="normal" />
              <SkiaPath
                path={skiaPath}
                color={strokeColor}
                style="stroke"
                strokeWidth={style.stroke_width}
                strokeCap={style.stroke_linecap}
                strokeJoin={style.stroke_linejoin}
                opacity={strokeOpacity}
              />
            </Group>
          ) : (
            <SkiaPath
              path={skiaPath}
              color={strokeColor}
              style="stroke"
              strokeWidth={style.stroke_width}
              strokeCap={style.stroke_linecap}
              strokeJoin={style.stroke_linejoin}
              opacity={strokeOpacity}
            />
          ))}
      </Group>
    );
  }

  if (points.length === 0) return null;

  // Single point = dot
  if (points.length === 1 && points[0]) {
    return <StrokeDot point={points[0]} style={style} />;
  }

  const fillColor = stroke.fill;
  const fillPath = fillColor ? Skia.Path.MakeFromSVGString(pathToSvgD(stroke, isPaintMode)) : null;
  const fillOpacity = fillColor ? (stroke.fill_opacity ?? style.opacity ?? 1) : undefined;

  if (fillColor && style.stroke_width <= 0) {
    return fillPath ? (
      <SkiaPath path={fillPath} color={fillColor} style="fill" opacity={fillOpacity} />
    ) : null;
  }

  // Freehand/painterly strokes. In paint mode, completed strokes use the
  // stamp-based painterly model (matches the server renderer).
  return (
    <Group>
      {fillPath && fillColor && (
        <SkiaPath path={fillPath} color={fillColor} style="fill" opacity={fillOpacity} />
      )}
      {isPaintMode ? (
        <SkiaStampedStroke points={points} style={style} brushName={stroke.brush} />
      ) : (
        <PainterlyStroke points={points} style={style} blur={0} />
      )}
    </Group>
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
        <MemoizedSkiaStroke
          key={index}
          stroke={stroke}
          styleConfig={styleConfig}
          isPaintMode={isPaintMode}
        />
      ))}
    </>
  );
});

/**
 * Skia-based renderer with GPU acceleration and painterly effects.
 */
export function SkiaRenderer({
  strokes,
  currentStroke,
  agentStroke,
  agentStrokeStyle,
  penPosition,
  penDown,
  styleConfig,
  showIdleAnimation,
  width,
  height,
  primaryColor,
}: RendererProps): React.ReactElement {
  const isPaintMode = styleConfig.type === 'paint';

  // Track actual layout size so we can map logical canvas coords to device points.
  // Skia Canvas renders in layout point space (unlike SVG which has viewBox).
  const [layoutSize, setLayoutSize] = useState({ width: 0, height: 0 });
  const handleLayout = useCallback((event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setLayoutSize((prev) =>
      prev.width === width && prev.height === height ? prev : { width, height }
    );
  }, []);

  const src = useMemo(() => rect(0, 0, width, height), [width, height]);
  const dst = useMemo(
    () => rect(0, 0, layoutSize.width || width, layoutSize.height || height),
    [layoutSize.width, layoutSize.height, width, height]
  );
  const transform = useMemo(() => fitbox('contain', src, dst), [src, dst]);

  return (
    <View style={styles.canvas} onLayout={handleLayout}>
      <Canvas style={styles.canvas}>
        <Group transform={transform}>
          {/* Idle animation particles */}
          <SkiaIdleParticles visible={showIdleAnimation} />

          {/* Completed strokes - memoized layer skips re-render during animation */}
          <CompletedStrokesLayer strokes={strokes} styleConfig={styleConfig} isPaintMode={isPaintMode} />

          {/* Current human stroke */}
          {currentStroke.length > 0 &&
            (currentStroke.length === 1 ? (
              <StrokeDot point={currentStroke[0]!} style={styleConfig.human_stroke} />
            ) : (
              <PainterlyStroke
                points={currentStroke}
                style={styleConfig.human_stroke}
                blur={isPaintMode ? 1 : 0}
              />
            ))}

          {/* Agent in-progress stroke - using optimized incremental renderer */}
          {agentStroke.length > 0 &&
            (() => {
              const style = getEffectiveAgentStrokeStyle(styleConfig, agentStrokeStyle);
              return agentStroke.length === 1 ? (
                <StrokeDot point={agentStroke[0]!} style={style} />
              ) : (
                <SkiaInProgressStroke points={agentStroke} style={style} blur={isPaintMode} />
              );
            })()}

          {/* Pen position indicator */}
          {penPosition && (
            <PenIndicator position={penPosition} penDown={penDown} color={primaryColor} />
          )}
        </Group>
      </Canvas>
    </View>
  );
}

const styles = StyleSheet.create({
  canvas: {
    flex: 1,
  },
});
