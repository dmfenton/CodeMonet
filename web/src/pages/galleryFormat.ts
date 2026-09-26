/**
 * Formatting helpers for gallery pages (SSR-safe: fixed locale and UTC).
 */

import type { PublicGalleryPiece } from '@code-monet/shared';

export function pieceHref(piece: Pick<PublicGalleryPiece, 'user_id' | 'id'>): string {
  return `/gallery/${piece.user_id}/${piece.id}`;
}

/** "Sep 24" or "Sep 24, 2026"; empty for unparseable input. */
export function formatShortDate(iso: string, { year = false }: { year?: boolean } = {}): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(year ? { year: 'numeric' } : {}),
    timeZone: 'UTC',
  });
}
