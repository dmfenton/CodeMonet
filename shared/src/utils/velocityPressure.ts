/**
 * Velocity-based pen pressure simulation for freehand stroke rendering.
 *
 * Derives a pressure factor from average inter-point spacing:
 * - Closer points = slower movement = more pressure = thicker stroke
 * - Farther points = faster movement = less pressure = thinner stroke
 */

import type { Point } from '../types';
import type { FreehandStrokeOptions } from '../renderer/freehand';

/**
 * Compute a pressure-adjusted copy of freehand options based on point spacing.
 *
 * @param points - The tail points to analyze for velocity
 * @param options - Base freehand options
 * @param fallbackSize - Fallback size if options.size is undefined
 * @returns New options with pressure-adjusted size, or original options if < 2 points
 */
export function applyVelocityPressure(
  points: Point[],
  options: FreehandStrokeOptions,
  fallbackSize: number
): FreehandStrokeOptions {
  if (points.length < 2) return options;

  let totalDist = 0;
  for (let i = 1; i < points.length; i++) {
    const dx = points[i]!.x - points[i - 1]!.x;
    const dy = points[i]!.y - points[i - 1]!.y;
    totalDist += Math.sqrt(dx * dx + dy * dy);
  }

  const avgDist = totalDist / (points.length - 1);
  const pressureFactor = Math.max(0.6, Math.min(1.2, 1.0 / (1 + avgDist * 0.015)));

  return { ...options, size: (options.size ?? fallbackSize) * pressureFactor };
}
