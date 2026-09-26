/**
 * Stage bar: the painter's passes for one version, sized by marks, filling
 * in as the version paints (done = accent, current = emphasis, pending = paper).
 */

import React from 'react';
import type { StageSegment } from '@code-monet/shared';

interface StageBarProps {
  segments: StageSegment[];
}

function segmentTitle(segment: StageSegment): string {
  const ops = segment.ops === null ? '' : ` · ${segment.ops.toLocaleString()} strokes`;
  return `${segment.label || 'stage'}${ops} · ${segment.state}`;
}

export function StageBar({ segments }: StageBarProps): React.ReactElement | null {
  if (segments.length === 0) return null;
  return (
    <div className="stage-bar" role="list" aria-label="Painting stages" data-testid="stage-bar">
      {segments.map((segment) => (
        <div
          key={segment.key}
          role="listitem"
          className={`stage-seg is-${segment.state}`}
          style={{ flexGrow: segment.weight, flexBasis: 0 }}
          title={segmentTitle(segment)}
        >
          <span className="stage-seg-bar" />
          <span className="stage-seg-label">{segment.label || '—'}</span>
        </div>
      ))}
    </div>
  );
}
