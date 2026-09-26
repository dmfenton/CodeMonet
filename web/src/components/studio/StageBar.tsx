/**
 * Stage bar: the painter's passes for one version, sized by marks, filling
 * in as the version paints (done = accent, current = emphasis, pending = paper).
 *
 * Per-segment labels show only when every segment fits its full label;
 * otherwise one caption sits under the bar (shared rule: stageLabelsFit /
 * stageBarCaption). Each segment keeps its full label as a hover title.
 */

import React, { useLayoutEffect, useMemo, useState } from 'react';
import type { StageSegment } from '@code-monet/shared';
import { stageBarCaption, stageLabelsFit } from '@code-monet/shared';

/** Must match .stage-bar gap and .stage-seg-label font in styles.css. */
const SEGMENT_GAP_PX = 4;
const LABEL_FONT = "500 11px 'IBM Plex Mono', 'SF Mono', Menlo, monospace";

let measureContext: CanvasRenderingContext2D | null | undefined;

function measureLabel(label: string): number {
  if (measureContext === undefined) {
    measureContext =
      typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d');
  }
  if (!measureContext) return label.length * 6.6; // mono ~0.6em per glyph
  measureContext.font = LABEL_FONT;
  return measureContext.measureText(label).width;
}

interface StageBarProps {
  segments: StageSegment[];
}

function segmentTitle(segment: StageSegment): string {
  const ops = segment.ops === null ? '' : ` · ${segment.ops.toLocaleString('en-US')} strokes`;
  return `${segment.label || 'stage'}${ops} · ${segment.state}`;
}

export function StageBar({ segments }: StageBarProps): React.ReactElement | null {
  // Callback ref: the bar only mounts once there are segments.
  const [bar, setBar] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    if (!bar) return;
    const update = (): void => setWidth(bar.getBoundingClientRect().width);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(bar);
    return (): void => observer.disconnect();
  }, [bar]);

  const labelsFit = useMemo(
    () => stageLabelsFit(segments, width, SEGMENT_GAP_PX, measureLabel),
    [segments, width]
  );

  if (segments.length === 0) return null;
  return (
    <div className="stage-bar-wrap">
      <div
        ref={setBar}
        className={`stage-bar${labelsFit ? '' : ' no-labels'}`}
        role="list"
        aria-label="Painting stages"
        data-testid="stage-bar"
      >
        {segments.map((segment) => (
          <div
            key={segment.key}
            role="listitem"
            className={`stage-seg is-${segment.state}`}
            style={{ flexGrow: segment.weight, flexBasis: 0 }}
            title={segmentTitle(segment)}
          >
            <span className="stage-seg-bar" />
            {labelsFit && <span className="stage-seg-label">{segment.label || '—'}</span>}
          </div>
        ))}
      </div>
      {!labelsFit && (
        <p className="stage-bar-caption mono-label" data-testid="stage-caption">
          {stageBarCaption(segments)}
        </p>
      )}
    </div>
  );
}
