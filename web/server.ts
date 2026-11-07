/**
 * Development server for the Code Monet web app: Vite middleware with HMR,
 * the /api and /ws proxies, and server rendering of every page with the same
 * renderPage() that pre-renders production's public pages
 * (src/prerender.ts, run by the Python server). Production has no Node server:
 * nginx serves the static build and the pre-rendered pages.
 */

import fs from 'node:fs';
import http, { type IncomingMessage } from 'node:http';
import type { Socket } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { createServer as createViteServer } from 'vite';
import type { GalleryPieceDetail, PublicGalleryPiece } from '@code-monet/shared';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = process.env.PORT || 5173;

// Backend API URL for SSR data fetching
const API_URL = process.env.API_URL || 'http://localhost:8000';

type EntryServer = typeof import('./src/entry-server');

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url);
    if (response.ok) return (await response.json()) as T;
  } catch (error) {
    console.error(`SSR data fetch failed for ${url}:`, error);
  }
  return null;
}

async function pageData(
  url: string,
  entry: EntryServer
): Promise<Parameters<EntryServer['renderPage']>[2]> {
  if (url === '/' || url.startsWith('/?')) {
    const pieces = await fetchJson<PublicGalleryPiece[]>(
      `${API_URL}/public/gallery?limit=${entry.HOMEPAGE_PIECES}`
    );
    return { galleryPieces: pieces ?? [] };
  }
  if (url === '/gallery' || url.startsWith('/gallery?')) {
    const pieces = await fetchJson<PublicGalleryPiece[]>(
      `${API_URL}/public/gallery?limit=${entry.GALLERY_PIECES}`
    );
    return { galleryPieces: pieces ?? [] };
  }
  const match = url.match(/^\/gallery\/([^/]+)\/([^/?]+)/);
  if (match) {
    const [, userId, pieceId] = match;
    const detail = await fetchJson<GalleryPieceDetail>(
      `${API_URL}/public/gallery/${userId}/${pieceId}/strokes`
    );
    if (detail) return entry.pieceData(userId, detail);
  }
  return {};
}

async function createServer(): Promise<void> {
  const app = express();
  // One http server for pages, the /ws proxy's upgrades and Vite's HMR socket.
  const server = http.createServer(app);

  // Our proxies mount BEFORE Vite's middlewares: in middlewareMode Vite has no
  // http server to take WebSocket upgrades, so its own server.proxy
  // (vite.config.ts, for the standalone `vite` dev server) must never see /api
  // or /ws here.
  app.use(
    '/api',
    createProxyMiddleware({
      target: API_URL,
      changeOrigin: true,
      pathRewrite: { '^/api': '' },
    })
  );
  const wsProxy = createProxyMiddleware({
    target: API_URL.replace(/^http/, 'ws'),
    ws: true,
    pathFilter: '/ws',
  });
  app.use(wsProxy);
  const upgradeWs: (req: IncomingMessage, socket: Socket, head: Buffer) => void = wsProxy.upgrade;

  const vite = await createViteServer({
    // HMR shares this server (no separate port 24678 to collide across worktrees);
    // Vite only answers its own 'vite-hmr' upgrades, the /ws proxy the rest.
    server: { middlewareMode: true, hmr: { server } },
    appType: 'custom',
  });
  app.use(vite.middlewares);

  // Server-render every other page (Express 5 catch-all syntax)
  app.use(async (req, res, next) => {
    const url = req.originalUrl;
    if (url.startsWith('/api') || url.startsWith('/ws')) {
      return next();
    }
    try {
      let template = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf-8');
      template = await vite.transformIndexHtml(url, template);
      const entry = (await vite.ssrLoadModule('/src/entry-server.tsx')) as EntryServer;
      const html = entry.renderPage(template, url, await pageData(url, entry));
      res.status(200).set({ 'Content-Type': 'text/html' }).end(html);
    } catch (e) {
      vite.ssrFixStacktrace(e as Error);
      next(e);
    }
  });

  server.on('upgrade', upgradeWs);
  server.listen(port, () => {
    console.log(`Dev server running at http://localhost:${port}`);
  });
}

createServer();
