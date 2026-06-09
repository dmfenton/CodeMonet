/**
 * Canvas component with stroke rendering and touch handling.
 *
 * This component handles gesture detection and delegates rendering
 * to the Skia renderer for GPU-accelerated drawing.
 */

import React, { useCallback, useMemo, useRef } from 'react';
import { LayoutChangeEvent, StyleSheet, Text, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';

import { screenToCanvas } from '../hooks/useCanvas';
import { SkiaRenderer } from '../renderers';
import type { DrawingStyleConfig, Path, Point, RendererProps, StrokeStyle } from '@code-monet/shared';
import { CANVAS_HEIGHT, CANVAS_WIDTH, PLOTTER_STYLE } from '@code-monet/shared';
import { borderRadius, spacing, typography, useTheme } from '../theme';

interface CanvasProps {
  strokes: Path[];
  currentStroke: Point[];
  agentStroke: Point[]; // Agent's in-progress stroke
  agentStrokeStyle?: Partial<StrokeStyle> | null; // Style override for in-progress agent stroke
  penPosition: Point | null;
  penDown: boolean;
  drawingEnabled: boolean;
  canvasWidth?: number;
  canvasHeight?: number;
  styleConfig?: DrawingStyleConfig; // Current drawing style (defaults to plotter)
  showIdleAnimation: boolean; // Whether to show idle particles
  onStrokeStart: (x: number, y: number) => void;
  onStrokeMove: (x: number, y: number) => void;
  onStrokeEnd: () => void;
}

export function Canvas({
  strokes,
  currentStroke,
  agentStroke,
  agentStrokeStyle,
  penPosition,
  penDown,
  drawingEnabled,
  canvasWidth = CANVAS_WIDTH,
  canvasHeight = CANVAS_HEIGHT,
  styleConfig = PLOTTER_STYLE,
  showIdleAnimation,
  onStrokeStart,
  onStrokeMove,
  onStrokeEnd,
}: CanvasProps): React.JSX.Element {
  const { colors, shadows } = useTheme();
  const containerRef = useRef<{ width: number; height: number }>({ width: 0, height: 0 });

  const handleLayout = useCallback((event: LayoutChangeEvent) => {
    containerRef.current = {
      width: event.nativeEvent.layout.width,
      height: event.nativeEvent.layout.height,
    };
  }, []);

  // Store callbacks in refs to avoid stale closures in gesture handlers
  // This prevents "Object is not a function" crashes when callbacks change
  const onStrokeStartRef = useRef(onStrokeStart);
  const onStrokeMoveRef = useRef(onStrokeMove);
  const onStrokeEndRef = useRef(onStrokeEnd);

  // Keep refs up to date
  onStrokeStartRef.current = onStrokeStart;
  onStrokeMoveRef.current = onStrokeMove;
  onStrokeEndRef.current = onStrokeEnd;

  const panGesture = useMemo(
    () =>
      Gesture.Pan()
        .enabled(drawingEnabled)
        .onStart((event) => {
          const { width, height } = containerRef.current;
          if (width > 0 && height > 0) {
            const point = screenToCanvas(event.x, event.y, width, height, canvasWidth, canvasHeight);
            // Use ref to get latest callback and guard against undefined
            if (typeof onStrokeStartRef.current === 'function') {
              onStrokeStartRef.current(point.x, point.y);
            }
          }
        })
        .onUpdate((event) => {
          const { width, height } = containerRef.current;
          if (width > 0 && height > 0) {
            const point = screenToCanvas(event.x, event.y, width, height, canvasWidth, canvasHeight);
            // Use ref to get latest callback and guard against undefined
            if (typeof onStrokeMoveRef.current === 'function') {
              onStrokeMoveRef.current(point.x, point.y);
            }
          }
        })
        .onEnd(() => {
          // Use ref to get latest callback and guard against undefined
          if (typeof onStrokeEndRef.current === 'function') {
            onStrokeEndRef.current();
          }
        }),
    [drawingEnabled, canvasWidth, canvasHeight]
  );

  // Build renderer props
  const rendererProps: RendererProps = {
    strokes,
    currentStroke,
    agentStroke,
    agentStrokeStyle: agentStrokeStyle ?? null,
    penPosition,
    penDown,
    styleConfig,
    showIdleAnimation,
    width: canvasWidth,
    height: canvasHeight,
    primaryColor: colors.primary,
  };

  return (
    <View
      style={[
        styles.container,
        { aspectRatio: canvasWidth / canvasHeight, backgroundColor: colors.canvasBackground },
        shadows.md,
      ]}
      onLayout={handleLayout}
      testID="canvas-view"
    >
      <GestureDetector gesture={panGesture}>
        <View style={styles.canvasWrapper}>
          <SkiaRenderer {...rendererProps} />

          {/* Drawing mode indicator */}
          {drawingEnabled && (
            <View style={[styles.drawingIndicator, { backgroundColor: colors.secondary }]}>
              <Text style={[styles.drawingIndicatorText, { color: colors.textOnPrimary }]}>
                Drawing Mode
              </Text>
            </View>
          )}
        </View>
      </GestureDetector>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
  },
  canvasWrapper: {
    flex: 1,
  },
  drawingIndicator: {
    position: 'absolute',
    top: spacing.sm,
    left: spacing.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderRadius: borderRadius.sm,
  },
  drawingIndicatorText: {
    ...typography.small,
    fontWeight: '600',
  },
});
