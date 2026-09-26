/**
 * SSR initial data is only used on the path it was rendered for.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { HelmetProvider } from 'react-helmet-async';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PublicGalleryPiece } from '@code-monet/shared';
import { AppRoutes } from '../routes';
import { ssrDataFor } from '../ssrData';

const piece: PublicGalleryPiece = {
  id: 'piece_000001',
  user_id: '00000000-0000-4000-8000-000000000001',
  piece_number: 1,
  stroke_count: 10,
  created_at: '2026-09-26T12:00:00Z',
  title: 'Homepage Only',
};

describe('ssrDataFor', () => {
  it('matches the rendered path only', () => {
    const data = { path: '/', galleryPieces: [piece] };
    expect(ssrDataFor(data, '/')).toBe(data);
    expect(ssrDataFor(data, '/gallery')).toBeUndefined();
    expect(ssrDataFor({ path: '/gallery/' }, '/gallery')).toBeDefined();
    expect(ssrDataFor({ galleryPieces: [piece] }, '/')).toBeUndefined();
    expect(ssrDataFor(undefined, '/')).toBeUndefined();
  });
});

describe('AppRoutes with SSR data', () => {
  afterEach(() => vi.unstubAllGlobals());

  const renderAt = (path: string, initialData: unknown): void => {
    render(
      <HelmetProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes initialData={initialData} />
        </MemoryRouter>
      </HelmetProvider>
    );
  };

  it("does not show the homepage's pieces on the gallery", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('[]', { headers: { 'content-type': 'application/json' } }))
    );
    renderAt('/gallery', { path: '/', galleryPieces: [piece] });
    await waitFor(() => expect(screen.getByText(/Nothing hangs here yet/)).toBeTruthy());
    expect(screen.queryByText('Homepage Only')).toBeNull();
  });

  it('uses data rendered for this path', () => {
    vi.stubGlobal('fetch', vi.fn());
    renderAt('/gallery', { path: '/gallery', galleryPieces: [piece] });
    expect(screen.getAllByText('Homepage Only').length).toBeGreaterThan(0);
    expect(fetch).not.toHaveBeenCalled();
  });
});
