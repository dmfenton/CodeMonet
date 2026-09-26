/**
 * Server-side entry point for SSR.
 * This file renders the app to HTML string on the server.
 */

import { StrictMode } from 'react';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router';
import { HelmetProvider, HelmetServerState } from 'react-helmet-async';
import { AuthProvider } from './context/AuthContext';
import { RendererProvider } from './context/RendererContext';
import type { GalleryPieceDetail, PublicGalleryPiece } from '@code-monet/shared';
import { AppRoutes } from './routes';

export interface SSRData {
  /** Pathname the data was rendered for; ignored on any other path. */
  path?: string;
  galleryPieces?: PublicGalleryPiece[];
  galleryPiece?: PublicGalleryPiece & { description?: string };
  pieceStrokes?: GalleryPieceDetail;
}

export interface RenderResult {
  html: string;
  helmet: HelmetServerState;
}

// Default helmet state for when context is not populated (uses toString only in SSR)
const emptyDatum = { toString: (): string => '' };
const defaultHelmet = {
  title: emptyDatum,
  meta: emptyDatum,
  link: emptyDatum,
  script: emptyDatum,
} as HelmetServerState;

export function render(url: string, initialData?: SSRData): RenderResult {
  const helmetContext: { helmet?: HelmetServerState } = {};

  const html = renderToString(
    <StrictMode>
      <HelmetProvider context={helmetContext}>
        <StaticRouter location={url}>
          <RendererProvider>
            <AuthProvider>
              <AppRoutes initialData={initialData} />
            </AuthProvider>
          </RendererProvider>
        </StaticRouter>
      </HelmetProvider>
    </StrictMode>
  );

  return {
    html,
    helmet: helmetContext.helmet ?? defaultHelmet,
  };
}
