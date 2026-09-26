/**
 * Public gallery: the latest piece hangs large, the rest in a grid.
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router';
import type { DrawingStyleType, PublicGalleryPiece } from '@code-monet/shared';
import { getApiUrl } from '../config';
import { Icon } from '../components/brand/Icon';
import { PieceCard } from '../components/site/PieceCard';
import { SiteFooter, SiteHeader } from '../components/site/SiteChrome';
import { formatShortDate } from './galleryFormat';

/** The public listing endpoint caps a page at 50 pieces. */
const GALLERY_LIMIT = 50;

type StyleFilter = 'all' | DrawingStyleType;

const FILTERS: { id: StyleFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'paint', label: 'Paint' },
  { id: 'plotter', label: 'Plotter' },
];

interface GalleryPageProps {
  initialGalleryPieces?: PublicGalleryPiece[];
}

function countLabel(pieces: PublicGalleryPiece[]): string {
  const n = pieces.length;
  const noun = n === 1 ? 'piece' : 'pieces';
  const count = n >= GALLERY_LIMIT ? `latest ${n} ${noun}` : `${n} ${noun}`;
  const oldest = pieces[pieces.length - 1]?.created_at;
  const since = oldest ? formatShortDate(oldest, { year: true }) : null;
  return since ? `${count} · since ${since}` : count;
}

export function GalleryPage({ initialGalleryPieces }: GalleryPageProps): React.ReactElement {
  const [pieces, setPieces] = useState<PublicGalleryPiece[]>(initialGalleryPieces ?? []);
  const [loading, setLoading] = useState(!initialGalleryPieces);
  const [filter, setFilter] = useState<StyleFilter>('all');

  useEffect(() => {
    if (initialGalleryPieces) return;
    const controller = new AbortController();
    fetch(`${getApiUrl()}/public/gallery?limit=${GALLERY_LIMIT}`, { signal: controller.signal })
      .then((response) => (response.ok ? (response.json() as Promise<PublicGalleryPiece[]>) : []))
      .then((data) => setPieces(data))
      .catch(() => {
        // Offline or aborted: show the empty state.
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return (): void => controller.abort();
  }, [initialGalleryPieces]);

  // Style filters need drawing_style on listing entries (not every server sends it).
  const canFilter = pieces.some((p) => p.drawing_style !== undefined);
  const shown =
    filter === 'all' ? pieces : pieces.filter((p) => (p.drawing_style ?? 'plotter') === filter);
  const [featured, ...rest] = shown;

  return (
    <div className="site gallery-page">
      <SiteHeader>
        <nav className="site-crumbs" aria-label="Breadcrumb">
          <Link to="/">Home</Link>
          <Icon name="right" className="crumb-sep" />
          <span aria-current="page">Gallery</span>
        </nav>
      </SiteHeader>

      <main className="site-section gallery-main">
        <header className="gallery-head">
          <h1 className="gallery-title">Gallery</h1>
          {!loading && pieces.length > 0 && <p className="mono-label">{countLabel(pieces)}</p>}
          {canFilter && (
            <div className="gallery-filters" role="group" aria-label="Filter by style">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className="chip"
                  aria-pressed={filter === f.id}
                  onClick={() => setFilter(f.id)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          )}
        </header>

        {loading ? (
          <div className="gallery-status">
            <div className="spinner" />
          </div>
        ) : shown.length === 0 ? (
          <div className="gallery-status">
            <p>
              {pieces.length === 0
                ? 'Nothing hangs here yet. Watch the painter make the first piece.'
                : 'No pieces in this style yet.'}
            </p>
            {pieces.length === 0 && (
              <Link to="/studio" className="btn btn-primary">
                Enter studio
              </Link>
            )}
          </div>
        ) : (
          <>
            {featured && (
              <div className="gallery-featured">
                <PieceCard piece={featured} featured />
              </div>
            )}
            {rest.length > 0 && (
              <ul className="art-grid">
                {rest.map((piece) => (
                  <li key={`${piece.user_id}/${piece.id}`}>
                    <PieceCard piece={piece} />
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>

      <SiteFooter />
    </div>
  );
}
