/**
 * Piece page: a painted piece's image is the program render only, so the
 * viewer's own marks are drawn as a vector overlay on top.
 */

import React from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { HelmetProvider } from 'react-helmet-async';
import { describe, expect, it } from 'vitest';
import type { GalleryPieceDetail, Path } from '@code-monet/shared';
import { GalleryPiecePage } from '../pages/GalleryPiecePage';

const stroke = (author: 'human' | 'agent'): Path =>
  ({
    type: 'polyline',
    points: [
      { x: 10, y: 10 },
      { x: 60, y: 40 },
    ],
    author,
  }) as Path;

const renderPiece = (detail: GalleryPieceDetail): HTMLElement =>
  render(
    <HelmetProvider>
      <MemoryRouter>
        <GalleryPiecePage
          userId="00000000-0000-4000-8000-000000000001"
          pieceId="piece_000001"
          initialStrokes={detail}
        />
      </MemoryRouter>
    </HelmetProvider>
  ).container;

const base: GalleryPieceDetail = {
  id: 'piece_000001',
  piece_number: 1,
  canvas_width: 800,
  canvas_height: 600,
  created_at: '2026-09-26T12:00:00Z',
  strokes: [],
};

describe('GalleryPiecePage human stroke overlay', () => {
  it('draws human strokes over a raster piece', () => {
    const container = renderPiece({
      ...base,
      format: 'raster',
      image_url: '/painting-assets/u/t/final.png',
      strokes: [stroke('human'), stroke('agent')],
    });

    expect(container.querySelector('.piece-frame img')).not.toBeNull();
    const overlay = container.querySelector('.piece-strokes-overlay');
    expect(overlay).not.toBeNull();
    expect(overlay?.querySelectorAll('path')).toHaveLength(1);
  });

  it('adds no overlay to a raster piece without human strokes', () => {
    const container = renderPiece({
      ...base,
      format: 'raster',
      image_url: '/painting-assets/u/t/final.png',
    });

    expect(container.querySelector('.piece-strokes-overlay')).toBeNull();
  });

  it('draws a vector piece as a single artwork, not an overlay', () => {
    const container = renderPiece({ ...base, format: 'strokes', strokes: [stroke('human')] });

    expect(container.querySelector('.piece-strokes-overlay')).toBeNull();
    expect(container.querySelectorAll('.piece-frame svg path')).toHaveLength(1);
  });
});
