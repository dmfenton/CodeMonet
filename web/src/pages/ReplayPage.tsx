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
 * Program-painting mode: ?raster=<asset_base>[&from=<asset_base>] plays a
 * rendered version (reveal.json + keyframes) through the production
 * RasterRevealLayer, optionally over a previous version's final image.
 * asset_base is either an API path (/painting-assets/<user>/<token>/, fetched
 * via the API base) or any other URL prefix ending in '/' (e.g. a copy under
 * web/public/replay-fixtures/, which is gitignored).
 */

import React, { useCallback, useEffect, useState } from 'react';
import type { PaintingVersionRef, Path } from '@code-monet/shared';
import { getStyleConfig } from '@code-monet/shared';
import { getApiUrl } from '../config';
import { RasterRevealLayer, type RevealPlaybackInfo } from '../renderers/RasterRevealLayer';
import { StampCanvasLayer } from '../renderers/StampCanvasLayer';

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

/** Resolve a ?raster/?from value to a URL prefix usable with apiUrl=''. */
function resolveAssetBase(value: string): string {
  const base = value.endsWith('/') ? value : `${value}/`;
  return base.startsWith('/painting-assets/') ? `${getApiUrl()}${base}` : base;
}

function versionRef(assetBase: string, version: number): PaintingVersionRef {
  // Dimensions are informational; the layer sizes from the logical canvas.
  return { piece_number: 0, version, asset_base: assetBase, image_width: 0, image_height: 0 };
}

function RasterReplay({
  raster,
  from,
}: {
  raster: string;
  from: string | null;
}): React.ReactElement {
  const [run, setRun] = useState(0);
  const [info, setInfo] = useState<RevealPlaybackInfo | null>(null);
  const [done, setDone] = useState(false);
  const base = from ? versionRef(resolveAssetBase(from), 0) : null;
  const playing = done ? null : versionRef(resolveAssetBase(raster), 1);
  const settled = done ? versionRef(resolveAssetBase(raster), 1) : base;

  const handleDone = useCallback(() => setDone(true), []);
  const replay = (): void => {
    setDone(false);
    setInfo(null);
    setRun((n) => n + 1);
  };

  return (
    <div style={{ padding: 16, fontFamily: 'sans-serif' }}>
      <div style={{ marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center' }}>
        <button onClick={replay}>Replay</button>
        <span data-testid="reveal-status">
          {done
            ? 'done'
            : info?.playing
              ? `keyframe ${info.keyframe} (${info.label}) · ${info.opsDone} ops`
              : 'loading…'}
        </span>
      </div>
      <div
        key={run}
        data-testid="replay-canvas"
        data-reveal-state={done ? 'done' : info?.playing ? 'playing' : 'loading'}
        style={{
          position: 'relative',
          width: 800,
          maxWidth: '100%',
          aspectRatio: '800 / 600',
          background: '#FFFFFF',
        }}
      >
        <RasterRevealLayer
          apiUrl=""
          base={settled}
          playing={playing}
          width={800}
          height={600}
          onPlaybackDone={handleDone}
          onProgress={setInfo}
        />
      </div>
    </div>
  );
}

export function ReplayPage(): React.ReactElement {
  const params = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search);
  const raster = params?.get('raster') ?? null;
  if (raster) return <RasterReplay raster={raster} from={params?.get('from') ?? null} />;
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
