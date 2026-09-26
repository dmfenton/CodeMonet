/**
 * Public piece page: the painting in a mat, its title and facts, the prompt,
 * a version-by-version replay, and the program that painted it.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import type {
  GalleryPieceDetail,
  Path,
  PaintingVersionRef,
  PaintingVersionSummary,
  PublicGalleryPiece,
  RevealPacing,
} from '@code-monet/shared';
import { pathToSvgDScaled, pieceDisplayTitle } from '@code-monet/shared';
import { getApiUrl, getPublicAssetUrl } from '../config';
import { Icon } from '../components/brand/Icon';
import { SiteFooter, SiteHeader } from '../components/site/SiteChrome';
import { RasterRevealLayer, type RevealPlaybackInfo } from '../renderers/RasterRevealLayer';
import { useRevealManifest } from '../renderers/revealManifest';
import { useDialogFocus } from '../hooks/useDialogFocus';
import { formatShortDate } from './galleryFormat';

interface GalleryPiecePageProps {
  userId: string;
  pieceId: string;
  initialPiece?: PublicGalleryPiece;
  initialStrokes?: GalleryPieceDetail;
}

/** Replay is brisker than live viewing: a few seconds per version. */
const REPLAY_PACING: RevealPacing = {
  strokeOpMs: 6,
  areaOpMs: 160,
  maxKeyframeMs: 2500,
  maxVersionMs: 9000,
};

/** Asset URLs are relative to the API base; the same during SSR and on the client. */
const ASSET_API = getPublicAssetUrl('');

function rasterImageUrl(data: GalleryPieceDetail | undefined): string | null {
  if (data?.format !== 'raster' || !data.image_url) return null;
  return getPublicAssetUrl(data.image_url);
}

const versionFinalUrl = (v: PaintingVersionSummary): string =>
  getPublicAssetUrl(`${v.asset_base}final.png`);

function toRef(v: PaintingVersionSummary, pieceNumber: number): PaintingVersionRef {
  return {
    piece_number: pieceNumber,
    version: v.version,
    asset_base: v.asset_base,
    image_width: v.image_width,
    image_height: v.image_height,
  };
}

function metaLine(
  detail: GalleryPieceDetail | undefined,
  piece: PublicGalleryPiece | undefined
): string {
  const created = detail?.created_at ?? piece?.created_at;
  const style = detail?.drawing_style ?? piece?.drawing_style;
  const versions = detail?.versions?.length ?? 0;
  const strokes = detail?.stroke_count ?? piece?.stroke_count;
  return [
    created ? formatShortDate(created, { year: true }) : null,
    style ?? null,
    versions > 0 ? `${versions} version${versions === 1 ? '' : 's'}` : null,
    strokes ? `${strokes.toLocaleString('en-US')} strokes` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

function VectorArtwork({
  strokes,
  width,
  height,
  title,
}: {
  strokes: Path[];
  width: number;
  height: number;
  title: string;
}): React.ReactElement {
  return (
    <svg viewBox={`0 0 ${width} ${height}`} aria-label={title} role="img">
      <rect width={width} height={height} fill="#fffdf8" />
      {strokes.map((stroke, i) => {
        const strokeWidth = stroke.stroke_width ?? (stroke.author === 'human' ? 4 : 3);
        const strokeColor =
          strokeWidth > 0
            ? (stroke.color ?? (stroke.author === 'human' ? '#9b4f45' : '#1a1d18'))
            : 'none';
        return (
          <path
            key={i}
            d={pathToSvgDScaled(stroke, 1)}
            fill={stroke.fill ?? 'none'}
            fillOpacity={stroke.fill ? (stroke.fill_opacity ?? stroke.opacity ?? 0.85) : undefined}
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeOpacity={stroke.opacity ?? 0.85}
          />
        );
      })}
    </svg>
  );
}

/** Replay position: which version, and whether it is animating. */
interface ReplayState {
  index: number;
  playing: boolean;
  /** Set once the viewer starts a replay; the static image shows until then. */
  started: boolean;
}

function ProgramDialog({
  version,
  onClose,
}: {
  version: PaintingVersionSummary;
  onClose: () => void;
}): React.ReactElement {
  const [program, setProgram] = useState<{ status: 'loading' | 'error' | 'ok'; text: string }>({
    status: 'loading',
    text: '',
  });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(getPublicAssetUrl(`${version.asset_base}painting.py`), { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setProgram({ status: 'ok', text: await res.text() });
      })
      .catch(() => {
        if (!controller.signal.aborted) setProgram({ status: 'error', text: '' });
      });
    return (): void => controller.abort();
  }, [version.asset_base]);

  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(dialogRef, onClose);

  const copy = (): void => {
    void navigator.clipboard?.writeText(program.text).then(() => setCopied(true));
  };

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        ref={dialogRef}
        className="dialog program-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="program-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="program-head">
          <h2 id="program-title" className="mono-label">
            painting.py · v{version.version}
          </h2>
          <div className="program-actions">
            {program.status === 'ok' && (
              <button type="button" className="btn btn-ghost" onClick={copy}>
                <Icon name="copy" /> {copied ? 'Copied' : 'Copy'}
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-icon"
              aria-label="Close"
              onClick={onClose}
            >
              <Icon name="close" />
            </button>
          </div>
        </div>
        {program.status === 'loading' && <div className="spinner" />}
        {program.status === 'error' && (
          <p className="program-error">The program for this version isn&apos;t available.</p>
        )}
        {program.status === 'ok' && (
          <pre className="code-card program-code">
            <code>{program.text}</code>
          </pre>
        )}
      </div>
    </div>
  );
}

export function GalleryPiecePage({
  userId,
  pieceId,
  initialPiece,
  initialStrokes,
}: GalleryPiecePageProps): React.ReactElement {
  const [detail, setDetail] = useState<GalleryPieceDetail | undefined>(initialStrokes);
  const [loading, setLoading] = useState(!initialStrokes);

  useEffect(() => {
    if (initialStrokes) return;
    const controller = new AbortController();
    fetch(`${getApiUrl()}/public/gallery/${userId}/${pieceId}/strokes`, {
      signal: controller.signal,
    })
      .then((res) => (res.ok ? (res.json() as Promise<GalleryPieceDetail>) : undefined))
      .then((data) => setDetail(data))
      .catch(() => {
        // Not found / offline: render the not-found state.
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return (): void => controller.abort();
  }, [userId, pieceId, initialStrokes]);

  const pieceNumber =
    detail?.piece_number ??
    initialPiece?.piece_number ??
    parseInt(pieceId.replace('piece_', ''), 10);
  const title = pieceDisplayTitle({
    title: detail?.title ?? initialPiece?.title,
    prompt: detail?.prompt ?? initialPiece?.prompt,
    pieceNumber,
  });
  const width = detail?.canvas_width ?? initialPiece?.width ?? 800;
  const height = detail?.canvas_height ?? initialPiece?.height ?? 600;
  const imageUrl = rasterImageUrl(detail);
  const strokes = (detail?.strokes ?? []) as Path[];
  const versions = useMemo(() => detail?.versions ?? [], [detail?.versions]);
  const prompt = detail?.prompt?.trim() || null;

  // ---- Replay -------------------------------------------------------------

  const [replay, setReplay] = useState<ReplayState>({ index: 0, playing: false, started: false });
  const latestIndex = Math.max(0, versions.length - 1);
  const index = replay.started ? Math.min(replay.index, latestIndex) : latestIndex;
  const current = versions[index] ?? null;
  const previous = index > 0 ? versions[index - 1]! : null;
  const [progress, setProgress] = useState(0);
  const manifest = useRevealManifest(
    ASSET_API,
    replay.playing && current ? current.asset_base : null
  );
  const manifestRef = useRef(manifest);
  manifestRef.current = manifest;

  const handleProgress = useCallback((info: RevealPlaybackInfo) => {
    const m = manifestRef.current;
    if (!info.playing || !m) return;
    const total = m.keyframes.reduce((sum, kf) => sum + kf.ops.length, 0);
    const done =
      m.keyframes.slice(0, info.keyframe).reduce((sum, kf) => sum + kf.ops.length, 0) +
      info.opsDone;
    setProgress(total > 0 ? Math.min(1, done / total) : 0);
  }, []);

  const handlePlaybackDone = useCallback(() => {
    setProgress(1);
    setReplay((r) =>
      r.index < latestIndex ? { ...r, index: r.index + 1, playing: true } : { ...r, playing: false }
    );
  }, [latestIndex]);

  const play = (): void => {
    setProgress(0);
    setReplay((r) => {
      const atEnd = !r.started || r.index >= latestIndex;
      return { index: atEnd ? 0 : r.index, playing: true, started: true };
    });
  };
  const pause = (): void => setReplay((r) => ({ ...r, playing: false }));
  const seek = (i: number): void => {
    setProgress(1);
    setReplay({ index: i, playing: false, started: true });
  };

  // Reset progress when a new version starts playing.
  useEffect(() => {
    if (replay.playing) setProgress(0);
  }, [replay.index, replay.playing]);

  const [programOpen, setProgramOpen] = useState(false);
  const [shareNote, setShareNote] = useState<string | null>(null);
  const share = async (): Promise<void> => {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: `${title} — Code Monet`, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShareNote('Link copied');
    } catch {
      // Share sheet dismissed or clipboard unavailable.
    }
  };
  useEffect(() => {
    if (!shareNote) return;
    const t = setTimeout(() => setShareNote(null), 2000);
    return (): void => clearTimeout(t);
  }, [shareNote]);

  const hasArtwork = Boolean(imageUrl) || strokes.length > 0 || versions.length > 0;
  // Under the reveal layer: the picture before the playing version (blank for v1).
  const staticSrc = !replay.started
    ? (imageUrl ?? (current ? versionFinalUrl(current) : null))
    : replay.playing
      ? previous
        ? versionFinalUrl(previous)
        : null
      : current
        ? versionFinalUrl(current)
        : imageUrl;
  const showVector = !staticSrc && !replay.started && strokes.length > 0;
  const fill =
    versions.length > 0 ? (index + (replay.playing ? progress : 1)) / versions.length : 0;

  return (
    <div className="site piece-page">
      <SiteHeader>
        <nav className="site-crumbs" aria-label="Breadcrumb">
          <Link to="/gallery">Gallery</Link>
          <Icon name="right" className="crumb-sep" />
          <span aria-current="page" className="crumb-current">
            {title}
          </span>
        </nav>
      </SiteHeader>

      <main className="site-section piece-main">
        {loading ? (
          <div className="gallery-status">
            <div className="spinner" />
          </div>
        ) : !hasArtwork ? (
          <div className="gallery-status">
            <h1 className="piece-title">Piece not found</h1>
            <p>It may have been removed, or its gallery is private.</p>
            <Link to="/gallery" className="btn btn-ghost">
              Browse the gallery
            </Link>
          </div>
        ) : (
          <article className="piece-layout">
            <div className="piece-art">
              <div className="mat piece-mat">
                <div className="piece-frame" style={{ aspectRatio: `${width} / ${height}` }}>
                  {staticSrc && <img src={staticSrc} alt={title} width={width} height={height} />}
                  {showVector && (
                    <VectorArtwork strokes={strokes} width={width} height={height} title={title} />
                  )}
                  {replay.playing && current && (
                    <RasterRevealLayer
                      apiUrl={ASSET_API}
                      base={previous ? toRef(previous, pieceNumber) : null}
                      playing={toRef(current, pieceNumber)}
                      width={width}
                      height={height}
                      pacing={REPLAY_PACING}
                      onProgress={handleProgress}
                      onPlaybackDone={handlePlaybackDone}
                    />
                  )}
                </div>
              </div>

              {versions.length > 0 && (
                <div className="replay" data-testid="replay">
                  <button
                    type="button"
                    className="replay-play"
                    aria-label={replay.playing ? 'Pause replay' : 'Replay version by version'}
                    onClick={replay.playing ? pause : play}
                  >
                    <Icon name={replay.playing ? 'pause' : 'play'} />
                  </button>
                  <div className="replay-track">
                    <span className="replay-fill" style={{ width: `${fill * 100}%` }} />
                    {versions.map((v, i) => (
                      <button
                        key={v.asset_base}
                        type="button"
                        className={`replay-tick${i === index ? ' is-current' : ''}`}
                        style={{ left: `${((i + 1) / versions.length) * 100}%` }}
                        aria-label={`Show version ${v.version}`}
                        aria-pressed={i === index}
                        onClick={() => seek(i)}
                      />
                    ))}
                  </div>
                  <span className="mono-label replay-label">
                    {replay.started ? 'replay' : 'final'} · v{current?.version ?? versions.length}{' '}
                    of {versions.length}
                  </span>
                </div>
              )}
            </div>

            <div className="piece-info">
              <h1 className="piece-title">{title}</h1>
              <p className="mono-label piece-meta">{metaLine(detail, initialPiece)}</p>

              {prompt && (
                <div className="piece-prompt">
                  <p className="mono-label">prompt</p>
                  <blockquote className="serif-italic">“{prompt}”</blockquote>
                </div>
              )}

              <div className="piece-actions">
                {current && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setProgramOpen(true)}
                  >
                    <Icon name="code" /> View program
                  </button>
                )}
                <button type="button" className="btn btn-ghost" onClick={() => void share()}>
                  <Icon name="share" /> Share
                </button>
                {shareNote && (
                  <span className="mono-label" role="status">
                    {shareNote}
                  </span>
                )}
              </div>

              <p className="piece-note">
                Painted autonomously by Code Monet, an AI painter built on Claude.{' '}
                <Link to="/studio">Watch it paint</Link>.
              </p>
            </div>
          </article>
        )}
      </main>

      <SiteFooter />

      {programOpen && current && (
        <ProgramDialog version={current} onClose={() => setProgramOpen(false)} />
      )}
    </div>
  );
}
