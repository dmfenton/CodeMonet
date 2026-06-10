/**
 * Pure canvas utility functions.
 */

import type { Path, Point } from '@code-monet/shared';
import { CANVAS_HEIGHT, CANVAS_WIDTH } from '@code-monet/shared';

/**
 * Convert screen coordinates to canvas coordinates.
 */
export const screenToCanvas = (
  screenX: number,
  screenY: number,
  containerWidth: number,
  containerHeight: number,
  canvasWidth: number = CANVAS_WIDTH,
  canvasHeight: number = CANVAS_HEIGHT
): Point => ({
  x: screenX * (canvasWidth / containerWidth),
  y: screenY * (canvasHeight / containerHeight),
});

/**
 * Convert canvas coordinates to screen coordinates.
 */
export const canvasToScreen = (
  canvasX: number,
  canvasY: number,
  containerWidth: number,
  containerHeight: number,
  canvasWidth: number = CANVAS_WIDTH,
  canvasHeight: number = CANVAS_HEIGHT
): Point => ({
  x: canvasX * (containerWidth / canvasWidth),
  y: canvasY * (containerHeight / canvasHeight),
});

/**
 * Convert a Path to an SVG path 'd' attribute string.
 */
export const pathToSvgD = (path: Path): string => {
  const { points, type } = path;

  if (points.length === 0) return '';

  const first = points[0] as Point;

  switch (type) {
    case 'line': {
      if (points.length < 2) return '';
      const p1 = points[1] as Point;
      return `M ${first.x} ${first.y} L ${p1.x} ${p1.y}`;
    }

    case 'polyline': {
      if (points.length < 2) return '';
      return (
        `M ${first.x} ${first.y} ` +
        points
          .slice(1)
          .map((p) => `L ${p.x} ${p.y}`)
          .join(' ')
      );
    }

    case 'quadratic': {
      if (points.length < 3) return '';
      const p1 = points[1] as Point;
      const p2 = points[2] as Point;
      return `M ${first.x} ${first.y} Q ${p1.x} ${p1.y} ${p2.x} ${p2.y}`;
    }

    case 'cubic': {
      if (points.length < 4) return '';
      const p1 = points[1] as Point;
      const p2 = points[2] as Point;
      const p3 = points[3] as Point;
      return `M ${first.x} ${first.y} C ${p1.x} ${p1.y} ${p2.x} ${p2.y} ${p3.x} ${p3.y}`;
    }

    default:
      return '';
  }
};

/**
 * Convert points array to SVG polyline 'd' attribute.
 */
export const pointsToPolylineD = (points: readonly Point[]): string => {
  if (points.length === 0) return '';

  const first = points[0] as Point;

  if (points.length === 1) {
    return `M ${first.x} ${first.y}`;
  }

  return (
    `M ${first.x} ${first.y} ` +
    points
      .slice(1)
      .map((p) => `L ${p.x} ${p.y}`)
      .join(' ')
  );
};
