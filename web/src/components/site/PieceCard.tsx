/**
 * Gallery card: server thumbnail in a mat, serif-italic title, mono date;
 * links to the piece page.
 */

import React from 'react';
import { Link } from 'react-router';
import type { PublicGalleryPiece } from '@code-monet/shared';
import { pieceDisplayTitle } from '@code-monet/shared';
import { getPublicAssetUrl } from '../../config';
import { formatShortDate, pieceHref } from '../../pages/galleryFormat';

export function thumbnailUrl(piece: PublicGalleryPiece): string {
  return getPublicAssetUrl(`/public/gallery/${piece.user_id}/${piece.id}/thumbnail.png`);
}

export function titleOf(piece: PublicGalleryPiece): string {
  return pieceDisplayTitle({
    title: piece.title,
    prompt: piece.prompt,
    pieceNumber: piece.piece_number,
  });
}

export function PieceCard({
  piece,
  featured = false,
}: {
  piece: PublicGalleryPiece;
  featured?: boolean;
}): React.ReactElement {
  const title = titleOf(piece);
  return (
    <Link to={pieceHref(piece)} className={`art-card${featured ? ' art-card-featured' : ''}`}>
      <div className="mat">
        <img
          src={thumbnailUrl(piece)}
          alt={title}
          width={piece.width ?? 800}
          height={piece.height ?? 600}
          loading={featured ? 'eager' : 'lazy'}
        />
      </div>
      <span className="art-card-meta">
        <span className="art-card-title">{title}</span>
        {piece.created_at && (
          <span className="mono-label">
            {formatShortDate(piece.created_at, { year: featured })}
          </span>
        )}
      </span>
    </Link>
  );
}
