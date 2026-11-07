/**
 * Pre-render the public pages as static HTML.
 *
 * Built as one self-contained bundle (dist/prerender/prerender.mjs, next to the
 * built index.html it uses as template) and run by the server
 * (server/code_monet/prerender.py) whenever the public gallery changes:
 *
 *   node prerender.mjs < {"pieces": [...], "details": {"<user>/<piece>": {...}}}
 *   -> {"pages": [{"path": "/", "html": "..."}, ...]}
 *
 * Each page is exactly what the old SSR server answered for that URL: the
 * rendered markup, its head tags and its initial data. nginx serves these
 * files, so visitors browse the gallery without waking the server.
 */

import type { GalleryPieceDetail, PublicGalleryPiece } from '@code-monet/shared';
import { GALLERY_PIECES, HOMEPAGE_PIECES, pieceData, renderPage } from './entry-server';

export interface PrerenderInput {
  /** Every public piece, newest first. */
  pieces: PublicGalleryPiece[];
  /** Public detail of each piece, keyed "<user_id>/<piece_id>". */
  details: Record<string, GalleryPieceDetail>;
}

export interface PrerenderedPage {
  path: string;
  html: string;
}

export function prerenderSite(template: string, input: PrerenderInput): PrerenderedPage[] {
  const page = (path: string, data: Parameters<typeof renderPage>[2]): PrerenderedPage => ({
    path,
    html: renderPage(template, path, data),
  });
  return [
    page('/', { galleryPieces: input.pieces.slice(0, HOMEPAGE_PIECES) }),
    page('/gallery', { galleryPieces: input.pieces.slice(0, GALLERY_PIECES) }),
    ...Object.entries(input.details).map(([key, detail]) => {
      const [userId, pieceId] = key.split('/');
      return page(`/gallery/${userId}/${pieceId}`, pieceData(userId, detail));
    }),
  ];
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString('utf-8');
}

async function main(): Promise<void> {
  const { readFile } = await import('node:fs/promises');
  const template = await readFile(new URL('./index.html', import.meta.url), 'utf-8');
  const input = JSON.parse(await readStdin()) as PrerenderInput;
  process.stdout.write(JSON.stringify({ pages: prerenderSite(template, input) }));
}

// Run only as the bundle's entry point, never when imported by tests.
if (import.meta.env.MODE === 'prerender') {
  main().catch((error: unknown) => {
    console.error(error);
    process.exit(1);
  });
}
