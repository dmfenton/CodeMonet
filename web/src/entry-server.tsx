/**
 * Server-side rendering: one page of the app as complete HTML.
 *
 * Production pre-renders the public pages with this module (src/prerender.ts,
 * run by the server whenever the public gallery changes); the dev server
 * (server.ts) renders every request with it. Both inject the same head tags,
 * markup and initial data into the built index.html.
 */

import { StrictMode } from 'react';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router';
import { HelmetProvider, HelmetServerState } from 'react-helmet-async';
import { AuthProvider } from './context/AuthContext';
import { RendererProvider } from './context/RendererContext';
import type { GalleryPieceDetail, PublicGalleryPiece } from '@code-monet/shared';
import { AppRoutes } from './routes';
import { safeJsonStringify } from './safeJson';

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

/** Latest pieces on the homepage and on the gallery page. */
export const HOMEPAGE_PIECES = 4;
export const GALLERY_PIECES = 50;

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

/** Initial data for a piece page, from its public detail. */
export function pieceData(userId: string, detail: GalleryPieceDetail): SSRData {
  return {
    galleryPiece: {
      id: detail.id,
      user_id: userId,
      piece_number: detail.piece_number,
      stroke_count: detail.stroke_count ?? detail.strokes?.length ?? 0,
      width: detail.canvas_width,
      height: detail.canvas_height,
      created_at: detail.created_at,
      ...(detail.title ? { title: detail.title } : {}),
      ...(detail.prompt ? { prompt: detail.prompt } : {}),
    },
    pieceStrokes: detail,
  };
}

/** The complete page for url: markup, initial data and head tags in the template. */
export function renderPage(template: string, url: string, data: SSRData): string {
  // Tag the data with the path it was rendered for; the client ignores it
  // after navigating elsewhere (routes.tsx).
  const initialData: SSRData = { ...data, path: url.split('?')[0] };
  const { html: appHtml, helmet } = render(url, initialData);
  return template
    .replace('<!--ssr-outlet-->', () => appHtml)
    .replace(
      '<!--ssr-initial-data-->',
      () => `<script>window.__INITIAL_DATA__ = ${safeJsonStringify(initialData)}</script>`
    )
    .replace('<!--helmet-title-->', () => helmet.title.toString())
    .replace('<!--helmet-meta-->', () => helmet.meta.toString())
    .replace('<!--helmet-link-->', () => helmet.link.toString())
    .replace('<!--helmet-script-->', () => helmet.script.toString());
}
