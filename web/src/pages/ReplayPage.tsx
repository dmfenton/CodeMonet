/**
 * ReplayPage — dev-only client-render harness.
 *
 * Renders a paths JSON export (scripts/render-study.py --json) with the
 * production stamp pipeline (StampCanvasLayer) so server (painting.py) and
 * client (stamping.ts) output can be compared pixel-for-pixel.
 *
 * Data sources, in order:
 *   1. window.__REPLAY_DATA__ (injected by Playwright in render-study --compare)
 *   2. ?src=<url> query param (fetched)
 *
 * Program-painting mode: ?perf=<performance.bin url>&speed=N[&from=<base image>]
 * plays a version's performance stream through the production
 * PerformancePlayer, optionally over a previous version's final image (e.g. a
 * copy under web/public/replay-fixtures/, which is gitignored).
 */

import React, { useCallback, useEffect, useState } from 'react';
import type { Path } from '@code-monet/shared';
import { getStyleConfig } from '@code-monet/shared';
import { StampCanvasLayer } from '../renderers/StampCanvasLayer';
import { PerformancePlayer, type PerformanceProgress } from '../renderers/PerformancePlayer';

interface ReplayData {
  width: number;
  height: number;
  paths: Path[];
  style?: 'paint' | 'plotter';
}

declare global {
  interface Window {
    __REPLAY_DATA__?: ReplayData;
  }
}

/** ?perf=<performance.bin url>&speed=20[&from=<base image url>]: the live pixel stream. */
function PerformanceReplay({
  src,
  base,
  speed,
}: {
  src: string;
  base: string | null;
  speed: number;
}): React.ReactElement {
  const [info, setInfo] = useState<PerformanceProgress | null>(null);
  const [done, setDone] = useState(false);
  const handleDone = useCallback(() => setDone(true), []);
  return (
    <div style={{ padding: 16, fontFamily: 'sans-serif' }}>
      <div style={{ marginBottom: 8 }}>
        <span data-testid="reveal-status">
          {done
            ? 'done'
            : info?.playing
              ? `${info.stage} · ${(info.handMs / 1000).toFixed(0)}s hand time · ${speed}x`
              : 'loading…'}
        </span>
      </div>
      <div
        data-testid="replay-canvas"
        data-reveal-state={done ? 'done' : info?.playing ? 'playing' : 'loading'}
        style={{ position: 'relative', width: 800, maxWidth: '100%', aspectRatio: '800 / 600' }}
      >
        <PerformancePlayer
          src={src}
          baseSrc={base}
          speed={speed}
          onProgress={setInfo}
          onDone={handleDone}
        />
      </div>
    </div>
  );
}

export function ReplayPage(): React.ReactElement {
  const params = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search);
  const perf = params?.get('perf') ?? null;
  if (perf)
    return (
      <PerformanceReplay
        src={perf}
        base={params?.get('from') ?? null}
        speed={Number(params?.get('speed') ?? 20) || 20}
      />
    );
  return <StrokeReplay />;
}

function StrokeReplay(): React.ReactElement {
  const [data, setData] = useState<ReplayData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (window.__REPLAY_DATA__) {
      setData(window.__REPLAY_DATA__);
      return;
    }
    const src = new URLSearchParams(window.location.search).get('src');
    if (!src) {
      setError('No data: set window.__REPLAY_DATA__ or pass ?src=<url>');
      return;
    }
    fetch(src)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setData((await res.json()) as ReplayData);
      })
      .catch((e: unknown) => setError(String(e)));
  }, []);

  // StampCanvasLayer paints in its own effect (child effects run before the
  // parent's); one extra frame ensures the canvas is committed before we
  // flip the ready marker that Playwright waits on.
  useEffect(() => {
    if (!data) return;
    const raf = requestAnimationFrame(() => setReady(true));
    return (): void => cancelAnimationFrame(raf);
  }, [data]);

  if (error) {
    return <div data-testid="replay-error">{error}</div>;
  }
  if (!data) {
    return <div>Loading replay data…</div>;
  }

  return (
    <div
      data-testid="replay-canvas"
      data-replay-ready={ready ? 'true' : 'false'}
      style={{
        position: 'relative',
        width: data.width,
        height: data.height,
        background: '#FFFFFF',
      }}
    >
      <StampCanvasLayer
        strokes={data.paths}
        styleConfig={getStyleConfig(data.style ?? 'paint')}
        width={data.width}
        height={data.height}
      />
    </div>
  );
}
