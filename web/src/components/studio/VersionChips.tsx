/**
 * Version chips v1…vN for the piece on the easel. The latest chip is the live
 * canvas; an older chip shows that version's final image.
 */

import React from 'react';
import type { PaintingVersionSummary } from '@code-monet/shared';

interface VersionChipsProps {
  versions: PaintingVersionSummary[];
  /** asset_base of the older version being viewed (null = live). */
  viewing: string | null;
  onSelect: (version: PaintingVersionSummary | null) => void;
}

export function VersionChips({
  versions,
  viewing,
  onSelect,
}: VersionChipsProps): React.ReactElement | null {
  if (versions.length === 0) return null;
  const latest = versions[versions.length - 1]!;
  return (
    <div className="version-chips" data-testid="version-chips">
      <span className="mono-label">versions</span>
      <div className="version-chips-list">
        {versions.map((v) => {
          const isLatest = v.asset_base === latest.asset_base;
          const isViewing = viewing === v.asset_base;
          const current = viewing === null ? isLatest : isViewing;
          return (
            <button
              key={v.asset_base}
              type="button"
              className={`version-chip${current ? ' is-current' : ''}${isLatest ? ' is-live' : ''}`}
              aria-pressed={current}
              title={
                isLatest
                  ? `v${v.version} · live`
                  : `Show v${v.version}${v.ops ? ` · ${v.ops.toLocaleString()} strokes` : ''}`
              }
              onClick={() => onSelect(isLatest ? null : v)}
            >
              v{v.version}
            </button>
          );
        })}
      </div>
    </div>
  );
}
