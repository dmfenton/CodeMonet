/**
 * Version history for the piece on the easel (paint mode).
 *
 * Seeded from `init.painting.versions` when the server provides it; otherwise
 * it remembers the versions seen this session. Reset on a new piece or clear.
 */

import type { InitPaintingRef, PaintingVersionRef, PaintingVersionSummary } from '../types';

export interface VersionHistory {
  /** Piece the versions belong to (null = none yet). */
  piece: number | null;
  /** Ascending by version number. */
  versions: PaintingVersionSummary[];
}

export const EMPTY_VERSION_HISTORY: VersionHistory = { piece: null, versions: [] };

export function summaryFromRef(
  ref: PaintingVersionRef,
  extra: Pick<PaintingVersionSummary, 'stages' | 'ops' | 'created_at'> = {}
): PaintingVersionSummary {
  const summary: PaintingVersionSummary = {
    version: ref.version,
    asset_base: ref.asset_base,
    image_width: ref.image_width,
    image_height: ref.image_height,
  };
  if (extra.stages !== undefined) summary.stages = extra.stages;
  if (extra.ops !== undefined) summary.ops = extra.ops;
  if (extra.created_at !== undefined) summary.created_at = extra.created_at;
  return summary;
}

/** Keep fields the newer record lacks (e.g. a bare init ref vs. a full summary). */
function mergeSummary(
  prev: PaintingVersionSummary,
  next: PaintingVersionSummary
): PaintingVersionSummary {
  return {
    ...prev,
    ...next,
    stages: next.stages ?? prev.stages,
    ops: next.ops ?? prev.ops,
    created_at: next.created_at ?? prev.created_at,
  };
}

/** Insert or update one version of `piece`; a different piece starts a new history. */
export function upsertVersion(
  history: VersionHistory,
  piece: number,
  summary: PaintingVersionSummary
): VersionHistory {
  const versions = history.piece === piece ? history.versions : [];
  const index = versions.findIndex((v) => v.version === summary.version);
  const next =
    index >= 0
      ? versions.map((v, i) => (i === index ? mergeSummary(v, summary) : v))
      : [...versions, summary].sort((a, b) => a.version - b.version);
  return { piece, versions: next };
}

/**
 * History after `init`: the server's list (when present) plus the current
 * version, merged with what this session already saw of the same piece.
 */
export function seedVersionHistory(
  existing: VersionHistory,
  painting: InitPaintingRef | null | undefined
): VersionHistory {
  if (!painting) return EMPTY_VERSION_HISTORY;
  const piece = painting.piece_number;
  let history: VersionHistory = existing.piece === piece ? existing : { piece, versions: [] };
  for (const summary of painting.versions ?? []) {
    history = upsertVersion(history, piece, summary);
  }
  return upsertVersion(history, piece, summaryFromRef(painting));
}

export function latestVersionNumber(history: VersionHistory): number {
  return history.versions[history.versions.length - 1]?.version ?? 0;
}
