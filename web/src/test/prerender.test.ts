/**
 * Pre-rendered public pages: the same head tags, markup and initial data the
 * SSR server produced, so link previews and search results are unchanged.
 */

import { describe, expect, it } from 'vitest';
import type { GalleryPieceDetail, PublicGalleryPiece } from '@code-monet/shared';
import { prerenderSite } from '../prerender';

const TEMPLATE = `<!doctype html><html><head>
<!--helmet-title-->
<!--helmet-meta-->
<!--helmet-link-->
<!--helmet-script-->
<title>Code Monet - Autonomous AI Artist</title>
</head><body><div id="root"><!--ssr-outlet--></div><!--ssr-initial-data--></body></html>`;

const USER = '00000000-0000-4000-8000-000000000001';

const piece = (n: number, title?: string): PublicGalleryPiece => ({
  id: `piece_${String(n).padStart(6, '0')}`,
  user_id: USER,
  piece_number: n,
  stroke_count: 12,
  created_at: `2026-10-${String(n).padStart(2, '0')}T00:00:00+00:00`,
  ...(title ? { title } : {}),
});

const detail = (n: number, title: string | null, prompt: string | null): GalleryPieceDetail => ({
  id: `piece_${String(n).padStart(6, '0')}`,
  strokes: [],
  piece_number: n,
  canvas_width: 800,
  canvas_height: 600,
  created_at: `2026-10-${String(n).padStart(2, '0')}T00:00:00+00:00`,
  title,
  prompt,
  stroke_count: 12,
  format: 'strokes',
});

const pages = (count: number): ReturnType<typeof prerenderSite> =>
  prerenderSite(TEMPLATE, {
    pieces: Array.from({ length: count }, (_, i) => piece(count - i, `Piece ${count - i}`)),
    details: {
      [`${USER}/piece_000002`]: detail(2, 'Lilies at Dusk', 'water lilies'),
      [`${USER}/piece_000003`]: detail(3, '</script><script>alert(1)</script> $& $1', null),
    },
  });

const page = (path: string): string => {
  const found = pages(60).find((p) => p.path === path);
  if (!found) throw new Error(`no page ${path}`);
  return found.html;
};

const initialData = (html: string): Record<string, unknown> => {
  const match = html.match(/window\.__INITIAL_DATA__ = (.*?)<\/script>/);
  if (!match) throw new Error('no initial data');
  return JSON.parse(match[1]) as Record<string, unknown>;
};

describe('prerenderSite', () => {
  it('renders the homepage, the gallery and every piece', () => {
    expect(pages(60).map((p) => p.path)).toEqual([
      '/',
      '/gallery',
      `/gallery/${USER}/piece_000002`,
      `/gallery/${USER}/piece_000003`,
    ]);
  });

  it('gives a piece page its Open Graph tags, canonical URL and structured data', () => {
    const html = page(`/gallery/${USER}/piece_000002`);
    const url = `https://monet.dmfenton.net/gallery/${USER}/piece_000002`;
    expect(html).toContain('property="og:title" content="Lilies at Dusk"');
    expect(html).toContain('property="og:type" content="article"');
    expect(html).toContain(
      `property="og:image" content="https://monet.dmfenton.net/api/public/gallery/${USER}/piece_000002/og-image.png"`
    );
    expect(html).toContain(`property="og:url" content="${url}"`);
    expect(html).toContain(`rel="canonical" href="${url}"`);
    expect(html).toContain('“water lilies” — painted by Code Monet');
    expect(html).toContain('"@type":"VisualArtwork"');
    expect(html).not.toContain('<!--ssr-outlet-->');
  });

  it('embeds the data the page would otherwise fetch from the server', () => {
    const data = initialData(page(`/gallery/${USER}/piece_000002`));
    expect(data.path).toBe(`/gallery/${USER}/piece_000002`);
    expect(data.pieceStrokes).toMatchObject({ id: 'piece_000002', title: 'Lilies at Dusk' });
    expect(data.galleryPiece).toMatchObject({ user_id: USER, piece_number: 2 });

    expect((initialData(page('/')).galleryPieces as unknown[]).length).toBe(4);
    expect((initialData(page('/gallery')).galleryPieces as unknown[]).length).toBe(50);
  });

  it('keeps an agent-written title inside its tags', () => {
    const html = page(`/gallery/${USER}/piece_000003`);
    expect(html).not.toContain('<script>alert(1)');
    expect(html).toContain(
      'property="og:title" content="&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt; $&amp; $1"'
    );
    expect(html).toContain('"name":"\\u003c/script\\u003e\\u003cscript\\u003ealert(1)');
    expect(initialData(html).pieceStrokes).toMatchObject({
      title: '</script><script>alert(1)</script> $& $1',
    });
  });

  it('lists the newest pieces in the gallery structured data', () => {
    const html = page('/gallery');
    expect(html).toContain('<title>Gallery - Code Monet</title>');
    expect(html).toContain('"numberOfItems":50');
    expect(html).toContain(`"url":"https://monet.dmfenton.net/gallery/${USER}/piece_000060"`);
  });
});
