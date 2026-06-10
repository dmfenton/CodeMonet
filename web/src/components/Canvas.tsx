/**
 * Canvas component for web - handles mouse input and delegates to renderer.
 *
 * This component handles mouse events and delegates rendering
 * to the appropriate renderer (SVG or Skia) based on configuration.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { DrawingStyleConfig, Path, Point, RendererProps, StrokeStyle } from '@code-monet/shared';
import { CANVAS_HEIGHT, CANVAS_WIDTH, PLOTTER_STYLE } from '@code-monet/shared';

import { useRendererConfig } from '../context/RendererContext';
import { SvgRenderer, FreehandSvgRenderer } from '../renderers';
import { StampCanvasLayer } from '../renderers/StampCanvasLayer';

interface CanvasProps {
  strokes: Path[];
  currentStroke: Point[];
  agentStroke: Point[];
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

/**
 * Convert screen coordinates to canvas coordinates.
 */
function screenToCanvas(
  clientX: number,
  clientY: number,
  rect: DOMRect,
  canvasWidth: number,
  canvasHeight: number
): Point {
  const scaleX = canvasWidth / rect.width;
  const scaleY = canvasHeight / rect.height;
  return {
    x: (clientX - rect.left) * scaleX,
    y: (clientY - rect.top) * scaleY,
  };
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
}: CanvasProps): React.ReactElement {
  const fitRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });
  const { config } = useRendererConfig();

  useEffect(() => {
    const fitEl = fitRef.current;
    if (!fitEl) return;

    const updateFrameSize = (): void => {
      const rect = fitEl.getBoundingClientRect();
      const availableWidth = rect.width;
      const availableHeight = rect.height;
      if (availableWidth <= 0 || availableHeight <= 0) return;

      const aspect = canvasWidth / canvasHeight;
      const availableAspect = availableWidth / availableHeight;
      if (availableAspect > aspect) {
        setFrameSize({
          width: availableHeight * aspect,
          height: availableHeight,
        });
      } else {
        setFrameSize({
          width: availableWidth,
          height: availableWidth / aspect,
        });
      }
    };

    updateFrameSize();
    const resizeObserver = new ResizeObserver(updateFrameSize);
    resizeObserver.observe(fitEl);
    return (): void => resizeObserver.disconnect();
  }, [canvasWidth, canvasHeight]);

  const getPoint = useCallback((e: React.MouseEvent): Point | null => {
    if (!svgRef.current) return null;
    const rect = svgRef.current.getBoundingClientRect();
    return screenToCanvas(e.clientX, e.clientY, rect, canvasWidth, canvasHeight);
  }, [canvasWidth, canvasHeight]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!drawingEnabled) return;
      const point = getPoint(e);
      if (point) {
        setIsDrawing(true);
        onStrokeStart(point.x, point.y);
      }
    },
    [drawingEnabled, getPoint, onStrokeStart]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDrawing || !drawingEnabled) return;
      const point = getPoint(e);
      if (point) {
        onStrokeMove(point.x, point.y);
      }
    },
    [isDrawing, drawingEnabled, getPoint, onStrokeMove]
  );

  const handleMouseUp = useCallback(() => {
    if (isDrawing) {
      setIsDrawing(false);
      onStrokeEnd();
    }
  }, [isDrawing, onStrokeEnd]);

  const handleMouseLeave = useCallback(() => {
    if (isDrawing) {
      setIsDrawing(false);
      onStrokeEnd();
    }
  }, [isDrawing, onStrokeEnd]);

  // In paint mode, completed strokes render on a raster stamp layer
  // (painterly, matches the server renderer); the SVG overlay keeps
  // in-progress strokes, the pen indicator, and idle animation.
  const useStampLayer = styleConfig.type === 'paint';

  // Build renderer props
  const rendererProps: RendererProps = {
    strokes: useStampLayer ? [] : strokes,
    currentStroke,
    agentStroke,
    agentStrokeStyle: agentStrokeStyle ?? null,
    penPosition,
    penDown,
    styleConfig,
    showIdleAnimation,
    width: canvasWidth,
    height: canvasHeight,
    primaryColor: styleConfig.human_stroke.color,
  };

  // Select renderer based on config
  // - 'svg': Basic SVG rendering (default)
  // - 'freehand': SVG with perfect-freehand natural strokes
  // - 'skia': GPU-accelerated (requires canvaskit-wasm)
  const Renderer: React.ComponentType<RendererProps> = ((): React.ComponentType<RendererProps> => {
    switch (config.renderer) {
      case 'freehand':
        return FreehandSvgRenderer;
      // case 'skia':
      //   return SkiaRenderer; // Uncomment when canvaskit is installed
      case 'svg':
      default:
        return SvgRenderer;
    }
  })();

  return (
    <div className="canvas-fit" ref={fitRef}>
      <div
        className="canvas-wrapper"
        data-testid="canvas-view"
        style={{
          width: frameSize.width || '100%',
          height: frameSize.height || '100%',
          aspectRatio: `${canvasWidth} / ${canvasHeight}`,
        }}
      >
        {useStampLayer && (
          <StampCanvasLayer
            strokes={strokes}
            styleConfig={styleConfig}
            width={canvasWidth}
            height={canvasHeight}
          />
        )}
        <svg
          ref={svgRef}
          width="100%"
          height="100%"
          viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
          preserveAspectRatio="xMidYMid meet"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
          style={{ cursor: drawingEnabled ? 'crosshair' : 'default' }}
        >
          <Renderer {...rendererProps} />
        </svg>

        {/* Drawing mode indicator */}
        {drawingEnabled && (
          <div
            style={{
              position: 'absolute',
              top: 8,
              left: 8,
              padding: '4px 8px',
              background: styleConfig.human_stroke.color,
              color: '#fff',
              borderRadius: 4,
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            Drawing Mode
          </div>
        )}
      </div>
    </div>
  );
}
