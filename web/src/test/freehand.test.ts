/**
 * Tests for the freehand path sampling and outline generation.
 *
 * These functions convert Path objects into sampled points for
 * the perfect-freehand library to render as natural brush strokes.
 */

import { describe, it, expect } from 'vitest';
import {
  samplePathPoints,
  getFreehandOutline,
  outlineToSvgPath,
  pointsToFreehandPath,
  DEFAULT_FREEHAND_OPTIONS,
} from '@code-monet/shared';
import type { Path, Point } from '@code-monet/shared';

// Helper to create test paths
function makePath(type: Path['type'], points: Point[]): Path {
  return { type, points };
}

describe('samplePathPoints', () => {
  describe('returns empty array for invalid inputs', () => {
    it('returns empty for svg path type', () => {
      const path = makePath('svg', [{ x: 0, y: 0 }]);
      expect(samplePathPoints(path)).toEqual([]);
    });

    it('returns empty for empty points array', () => {
      const path = makePath('line', []);
      expect(samplePathPoints(path)).toEqual([]);
    });
  });

  describe('line paths', () => {
    it('returns original points if fewer than 2', () => {
      const path = makePath('line', [{ x: 10, y: 20 }]);
      expect(samplePathPoints(path)).toEqual([{ x: 10, y: 20 }]);
    });

    it('samples line segments based on maxSegmentLength', () => {
      // Line from (0,0) to (100,0) = 100px long
      // With default maxSegmentLength of 8, should get ~13 segments (100/8 = 12.5)
      const path = makePath('line', [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
      ]);
      const sampled = samplePathPoints(path);

      // Should have more points than the original 2
      expect(sampled.length).toBeGreaterThan(2);

      // First and last should match original
      expect(sampled[0]).toEqual({ x: 0, y: 0 });
      expect(sampled[sampled.length - 1]).toEqual({ x: 100, y: 0 });

      // All points should be on the line (y = 0)
      for (const point of sampled) {
        expect(point.y).toBe(0);
      }
    });

    it('respects custom maxSegmentLength', () => {
      const path = makePath('line', [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
      ]);

      // Larger segments = fewer points
      const sampledLarge = samplePathPoints(path, 50);
      const sampledSmall = samplePathPoints(path, 10);

      expect(sampledSmall.length).toBeGreaterThan(sampledLarge.length);
    });
  });

  describe('quadratic paths', () => {
    it('returns original points if fewer than 3', () => {
      const path = makePath('quadratic', [
        { x: 0, y: 0 },
        { x: 50, y: 50 },
      ]);
      expect(samplePathPoints(path)).toEqual([
        { x: 0, y: 0 },
        { x: 50, y: 50 },
      ]);
    });

    it('samples quadratic Bezier curves', () => {
      // Quadratic curve from (0,0) to (100,0) with control point at (50, 100)
      const path = makePath('quadratic', [
        { x: 0, y: 0 },
        { x: 50, y: 100 }, // Control point - curve will bow downward
        { x: 100, y: 0 },
      ]);
      const sampled = samplePathPoints(path);

      // Should have minimum curve segments (12 by default)
      expect(sampled.length).toBeGreaterThanOrEqual(12);

      // First and last should match endpoints
      expect(sampled[0]).toEqual({ x: 0, y: 0 });
      expect(sampled[sampled.length - 1]).toEqual({ x: 100, y: 0 });

      // Midpoint should be pulled toward control point
      const midIndex = Math.floor(sampled.length / 2);
      expect(sampled[midIndex]!.y).toBeGreaterThan(0); // Curve bows downward
    });
  });

  describe('cubic paths', () => {
    it('returns original points if fewer than 4', () => {
      const path = makePath('cubic', [
        { x: 0, y: 0 },
        { x: 33, y: 50 },
        { x: 66, y: 50 },
      ]);
      expect(samplePathPoints(path)).toEqual([
        { x: 0, y: 0 },
        { x: 33, y: 50 },
        { x: 66, y: 50 },
      ]);
    });

    it('samples cubic Bezier curves', () => {
      // S-curve: start at (0,0), control points create S, end at (100,0)
      const path = makePath('cubic', [
        { x: 0, y: 0 },
        { x: 25, y: 50 }, // First control point
        { x: 75, y: -50 }, // Second control point
        { x: 100, y: 0 },
      ]);
      const sampled = samplePathPoints(path);

      // Should have minimum curve segments
      expect(sampled.length).toBeGreaterThanOrEqual(12);

      // Endpoints should match
      expect(sampled[0]).toEqual({ x: 0, y: 0 });
      expect(sampled[sampled.length - 1]).toEqual({ x: 100, y: 0 });
    });
  });

  describe('polyline paths', () => {
    it('returns original points unchanged', () => {
      const points = [
        { x: 0, y: 0 },
        { x: 10, y: 10 },
        { x: 20, y: 0 },
        { x: 30, y: 10 },
      ];
      const path = makePath('polyline', points);
      expect(samplePathPoints(path)).toEqual(points);
    });
  });
});

describe('getFreehandOutline', () => {
  it('returns empty array for empty input', () => {
    expect(getFreehandOutline([])).toEqual([]);
  });

  it('generates outline for single point (dot)', () => {
    const outline = getFreehandOutline([{ x: 50, y: 50 }]);
    // Single point should still generate an outline (small circle/dot)
    expect(outline.length).toBeGreaterThan(0);
  });

  it('generates closed polygon outline for stroke', () => {
    const points: Point[] = [
      { x: 0, y: 0 },
      { x: 50, y: 0 },
      { x: 100, y: 0 },
    ];
    const outline = getFreehandOutline(points);

    // Should generate outline points
    expect(outline.length).toBeGreaterThan(0);

    // All points should have x, y coordinates
    for (const point of outline) {
      expect(typeof point.x).toBe('number');
      expect(typeof point.y).toBe('number');
      expect(Number.isFinite(point.x)).toBe(true);
      expect(Number.isFinite(point.y)).toBe(true);
    }
  });

  it('respects stroke size option', () => {
    const points: Point[] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
    ];

    const thinOutline = getFreehandOutline(points, { ...DEFAULT_FREEHAND_OPTIONS, size: 4 });
    const thickOutline = getFreehandOutline(points, { ...DEFAULT_FREEHAND_OPTIONS, size: 20 });

    // Calculate bounding box heights (rough measure of stroke width)
    const thinYs = thinOutline.map((p) => p.y);
    const thickYs = thickOutline.map((p) => p.y);

    const thinHeight = Math.max(...thinYs) - Math.min(...thinYs);
    const thickHeight = Math.max(...thickYs) - Math.min(...thickYs);

    // Thick stroke should have larger outline spread
    expect(thickHeight).toBeGreaterThan(thinHeight);
  });
});

describe('outlineToSvgPath', () => {
  it('returns empty string for empty outline', () => {
    expect(outlineToSvgPath([])).toBe('');
  });

  it('generates valid SVG path with M, L commands and Z close', () => {
    const outline: Point[] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 50 },
      { x: 0, y: 50 },
    ];
    const path = outlineToSvgPath(outline);

    // Should start with M (moveto)
    expect(path).toMatch(/^M \d+\.\d+ \d+\.\d+/);

    // Should contain L (lineto) commands
    expect(path).toContain(' L ');

    // Should end with Z (close path)
    expect(path).toMatch(/Z$/);
  });

  it('formats coordinates with 2 decimal places', () => {
    const outline: Point[] = [
      { x: 1.23456, y: 7.89012 },
      { x: 3.14159, y: 2.71828 },
    ];
    const path = outlineToSvgPath(outline);

    expect(path).toBe('M 1.23 7.89 L 3.14 2.72 Z');
  });
});

describe('pointsToFreehandPath', () => {
  it('returns empty string for empty input', () => {
    expect(pointsToFreehandPath([])).toBe('');
  });

  it('combines outline generation and SVG conversion', () => {
    const points: Point[] = [
      { x: 0, y: 0 },
      { x: 50, y: 0 },
      { x: 100, y: 0 },
    ];
    const path = pointsToFreehandPath(points);

    // Should be a valid SVG path
    expect(path).toMatch(/^M /);
    expect(path).toMatch(/Z$/);
  });
});
