/**
 * Canvas picks the raster reveal layer for program paintings in paint mode.
 */

import React from 'react';
import { render } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import type { DrawingStyleConfig, PaintingState, Path } from '@code-monet/shared';
import { PAINT_STYLE, PLOTTER_STYLE } from '@code-monet/shared';

import { Canvas } from '../components/Canvas';

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
});

const painting: PaintingState = {
  base: {
    piece_number: 1,
    version: 1,
    asset_base: '/painting-assets/u/t/',
    image_width: 1600,
    image_height: 1200,
  },
  playing: null,
};

const strokes: Path[] = [
  {
    type: 'polyline',
    points: [
      { x: 0, y: 0 },
      { x: 10, y: 10 },
    ],
    author: 'agent',
  },
  {
    type: 'polyline',
    points: [
      { x: 5, y: 5 },
      { x: 20, y: 20 },
    ],
    author: 'human',
  },
];

const renderCanvas = (styleConfig: DrawingStyleConfig, p?: PaintingState): HTMLElement =>
  render(
    <Canvas
      strokes={strokes}
      currentStroke={[]}
      agentStroke={[]}
      penPosition={{ x: 1, y: 1 }}
      penDown={false}
      drawingEnabled={false}
      styleConfig={styleConfig}
      showIdleAnimation={false}
      painting={p}
      apiUrl="/api"
      onStrokeStart={() => {}}
      onStrokeMove={() => {}}
      onStrokeEnd={() => {}}
    />
  ).container;

describe('Canvas raster branch', () => {
  it('uses the raster layer and only vector human strokes when a painting exists', () => {
    const el = renderCanvas(PAINT_STYLE, painting);
    expect(el.querySelector('[data-testid="raster-reveal-layer"]')).not.toBeNull();
    expect(el.querySelectorAll('svg path').length).toBe(1);
  });

  it('keeps the stamp layer in paint mode without a painting', () => {
    const el = renderCanvas(PAINT_STYLE, { base: null, playing: null });
    expect(el.querySelector('[data-testid="raster-reveal-layer"]')).toBeNull();
    expect(el.querySelector('canvas')).not.toBeNull();
  });

  it('ignores paintings in plotter mode', () => {
    const el = renderCanvas(PLOTTER_STYLE, painting);
    expect(el.querySelector('[data-testid="raster-reveal-layer"]')).toBeNull();
  });
});
