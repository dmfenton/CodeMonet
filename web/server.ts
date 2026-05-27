/**
 * SSR Express server for Code Monet web app.
 *
 * In development: Uses Vite's middleware for HMR and on-demand compilation.
 * In production: Serves pre-built static assets with SSR rendering.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import compression from 'compression';
import sirv from 'sirv';
import type { ViteDevServer } from 'vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isProduction = process.env.NODE_ENV === 'production';
const port = process.env.PORT || 5173;

// Backend API URL for SSR data fetching
const API_URL = process.env.API_URL || 'http://localhost:8000';

interface SSRModule {
  render: (
    url: string,
    initialData?: Record<string, unknown>
  ) => { html: string; helmet: HelmetServerState };
}

interface HelmetServerState {
  title: { toString: () => string };
  meta: { toString: () => string };
  link: { toString: () => string };
  script: { toString: () => string };
}

interface GalleryPiece {
  id: string;
  user_id: string;
  piece_number: number;
  stroke_count: number;
  created_at: string;
  title?: string;
}

interface PieceStrokes {
  id: string;
  strokes: unknown[];
  piece_number: number;
  created_at: string;
}

/**
 * Safely stringify JSON for embedding in HTML script tags.
 * Escapes characters that could break out of script context or cause parsing issues.
 */
function safeJsonStringify(data: unknown): string {
  return JSON.stringify(data)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

async function fetchGalleryPieces(limit = 6): Promise<GalleryPiece[]> {
  try {
    const response = await fetch(`${API_URL}/public/gallery?limit=${limit}`);
    if (response.ok) {
      return await response.json();
    }
  } catch (error) {
    console.error('Failed to fetch gallery pieces for SSR:', error);
  }
  return [];
}

async function fetchPieceStrokes(userId: string, pieceId: string): Promise<PieceStrokes | null> {
  try {
    const response = await fetch(`${API_URL}/public/gallery/${userId}/${pieceId}/strokes`);
    if (response.ok) {
      return await response.json();
    }
  } catch (error) {
    console.error('Failed to fetch piece strokes for SSR:', error);
  }
  return null;
}

async function createServer(): Promise<void> {
  const app = express();

  let vite: ViteDevServer | undefined;
  let template: string;
  let ssrModule: SSRModule;

  if (!isProduction) {
    // Development mode: use Vite's middleware
    const { createServer: createViteServer } = await import('vite');
    vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'custom',
    });
    app.use(vite.middlewares);

    // Proxy API requests in development
    const { createProxyMiddleware } = await import('http-proxy-middleware');
    app.use(
      '/api',
      createProxyMiddleware({
        target: 'http://localhost:8000',
        changeOrigin: true,
        pathRewrite: { '^/api': '' },
      })
    );
    app.use(
      '/ws',
      createProxyMiddleware({
        target: 'ws://localhost:8000',
        ws: true,
      })
    );
  } else {
    // Production mode: serve static assets
    app.use(compression());
    app.use(sirv(path.join(__dirname, 'dist/client'), { extensions: [] }));
  }

  // Health check endpoint for load balancers and container orchestration
  app.get('/health', (req, res) => {
    res.status(200).json({
      status: 'healthy',
      version: process.env.VERSION || 'dev',
      timestamp: new Date().toISOString(),
    });
  });

  // SEO sitemap — robots.txt already advertises this URL. Includes the
  // static public routes plus every gallery piece we can enumerate via
  // the same /public/gallery endpoint the homepage uses for SSR.
  app.get('/sitemap.xml', async (_req, res) => {
    const base = 'https://monet.dmfenton.net';
    const pieces = await fetchGalleryPieces(200);
    const entries = [
      { loc: `${base}/`, changefreq: 'daily', priority: '1.0' },
      { loc: `${base}/gallery`, changefreq: 'hourly', priority: '0.9' },
      ...pieces.map((p) => ({
        loc: `${base}/gallery/${p.user_id}/${p.id}`,
        lastmod: p.created_at,
        changefreq: 'monthly',
        priority: '0.6',
      })),
    ];
    const body =
      '<?xml version="1.0" encoding="UTF-8"?>' +
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
      entries
        .map((e) => {
          const lastmod = 'lastmod' in e && e.lastmod ? `<lastmod>${e.lastmod}</lastmod>` : '';
          return `<url><loc>${e.loc}</loc>${lastmod}<changefreq>${e.changefreq}</changefreq><priority>${e.priority}</priority></url>`;
        })
        .join('') +
      '</urlset>';
    res
      .status(200)
      .set({ 'Content-Type': 'application/xml; charset=utf-8', 'Cache-Control': 'public, max-age=300' })
      .end(body);
  });

  // SSR handler for all routes (Express 5 catch-all syntax)
  app.use(async (req, res, next) => {
    const url = req.originalUrl;

    // Skip API and WebSocket routes
    if (url.startsWith('/api') || url.startsWith('/ws')) {
      return next();
    }

    try {
      // Load template
      if (!isProduction) {
        template = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
        template = await vite!.transformIndexHtml(url, template);
        ssrModule = (await vite!.ssrLoadModule('/src/entry-server.tsx')) as SSRModule;
      } else {
        // In production, use cached template
        if (!template) {
          template = fs.readFileSync(path.join(__dirname, 'dist/client/index.html'), 'utf-8');
        }
        if (!ssrModule) {
          ssrModule = (await import('./dist/server/entry-server.js')) as SSRModule;
        }
      }

      // Fetch SSR data based on route
      let initialData: Record<string, unknown> = {};

      if (url === '/' || url.startsWith('/?')) {
        // Homepage: fetch gallery preview
        const galleryPieces = await fetchGalleryPieces(6);
        initialData = { galleryPieces };
      } else if (url === '/gallery' || url.startsWith('/gallery?')) {
        // Gallery page: fetch more pieces
        const galleryPieces = await fetchGalleryPieces(50);
        initialData = { galleryPieces };
      } else if (url.match(/^\/gallery\/[^/]+\/[^/]+/)) {
        // Individual piece page
        const match = url.match(/^\/gallery\/([^/]+)\/([^/?]+)/);
        if (match) {
          const [, userId, pieceId] = match;
          const pieceStrokes = await fetchPieceStrokes(userId, pieceId);
          if (pieceStrokes) {
            initialData = {
              galleryPiece: {
                id: pieceStrokes.id,
                user_id: userId,
                piece_number: pieceStrokes.piece_number,
                stroke_count: pieceStrokes.strokes?.length ?? 0,
                created_at: pieceStrokes.created_at,
              },
              pieceStrokes,
            };
          }
        }
      }

      // Render the app
      const { html: appHtml, helmet } = ssrModule.render(url, initialData);

      // Inject rendered content into template
      let html = template
        .replace('<!--ssr-outlet-->', appHtml)
        .replace(
          '<!--ssr-initial-data-->',
          `<script>window.__INITIAL_DATA__ = ${safeJsonStringify(initialData)}</script>`
        );

      // Inject helmet tags
      if (helmet) {
        html = html
          .replace('<!--helmet-title-->', helmet.title.toString())
          .replace('<!--helmet-meta-->', helmet.meta.toString())
          .replace('<!--helmet-link-->', helmet.link.toString())
          .replace('<!--helmet-script-->', helmet.script.toString());
      }

      res.status(200).set({ 'Content-Type': 'text/html' }).end(html);
    } catch (e) {
      if (!isProduction && vite) {
        vite.ssrFixStacktrace(e as Error);
      }
      console.error('SSR Error:', e);

      // In production, serve fallback with 500 status for monitoring
      if (isProduction) {
        console.error('SSR Error (serving client fallback):', e);
        const fallback = fs.readFileSync(path.join(__dirname, 'dist/client/index.html'), 'utf-8');
        res.status(500).set({ 'Content-Type': 'text/html' }).end(fallback);
      } else {
        next(e);
      }
    }
  });

  app.listen(port, () => {
    console.log(`SSR server running at http://localhost:${port}`);
  });
}

createServer();
