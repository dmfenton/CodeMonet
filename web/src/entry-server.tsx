/**
 * Server-side entry point for SSR.
 * This file renders the app to HTML string on the server.
 */

import { StrictMode } from 'react';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { HelmetProvider, HelmetServerState } from 'react-helmet-async';
import { AuthProvider } from './context/AuthContext';
import { RendererProvider } from './context/RendererContext';
import { AppRoutes } from './routes';

export interface SSRData {
  galleryPieces?: GalleryPieceData[];
  galleryPiece?: GalleryPieceData;
  pieceStrokes?: PieceStrokesData;
}

export interface GalleryPieceData {
  id: string;
  user_id: string;
  piece_number: number;
  stroke_count: number;
  width?: number;
  height?: number;
  created_at: string;
  title?: string;
  description?: string;
}

export interface PieceStrokesData {
  id: string;
  strokes: PathData[];
  piece_number: number;
  canvas_width?: number;
  canvas_height?: number;
  created_at: string;
}

export type PathDataType = 'line' | 'quadratic' | 'cubic' | 'polyline' | 'svg';

export interface PathData {
  type: PathDataType;
  points?: { x: number; y: number }[];
  d?: string;
  author?: string;
  color?: string;
  stroke_width?: number;
  opacity?: number;
  fill?: string;
  fill_opacity?: number;
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
