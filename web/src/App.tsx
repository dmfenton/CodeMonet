/**
 * Studio: the canvas on a paper panel with its stage bar and version chips,
 * and the notebook docked beside it.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import type {
  DrawingStyleType,
  PaintingVersionSummary,
  PendingStroke,
  ServerMessage,
} from '@code-monet/shared';
import {
  PAINTING_FINAL_FILE,
  buildStageBar,
  deriveAgentStatus,
  deriveStudioPhase,
  fetchStrokesWithRetry,
  getLastToolCall,
  getStyleConfig,
  isActivePhase,
  notebookVersions,
  paintingAssetUrl,
  pieceDisplayTitle,
  shouldShowIdleAnimation,
  stagesFromLabels,
  stagesFromManifest,
  useCanvas,
  usePerformer,
} from '@code-monet/shared';
import { getApiUrl } from './config';

import { Canvas } from './components/Canvas';
import { DebugPanel } from './components/DebugPanel';
import { BrandMark } from './components/brand/BrandMark';
import { Icon } from './components/brand/Icon';
import { NewPieceDialog, type CanvasDimensions } from './components/studio/NewPieceDialog';
import { Notebook } from './components/studio/Notebook';
import { StageBar } from './components/studio/StageBar';
import { StudioMenu } from './components/studio/StudioMenu';
import { VersionChips } from './components/studio/VersionChips';
import type { RevealPlaybackInfo } from './renderers/RasterRevealLayer';
import { useRevealManifest } from './renderers/revealManifest';
import { useWebSocket } from './hooks/useWebSocket';
import { useDebug } from './hooks/useDebug';
import { useAuth } from './context/AuthContext';

interface DevState {
  strokesPainted: number;
  bufferLength: number;
  revealedChars: number;
  paused: boolean;
  pieceNumber: number;
  /** Program painting: version shown or being revealed (null = none). */
  paintingVersion: number | null;
  /** Keyframe being revealed (-1 when not playing). */
  revealKeyframe: number;
  /** Ops of that keyframe revealed so far. */
  revealOpsDone: number;
  revealPlaying: boolean;
}

const IDLE_REVEAL: RevealPlaybackInfo = {
  version: null,
  keyframe: -1,
  label: '',
  opsDone: 0,
  playing: false,
};

/** Version being revealed and its keyframe (changes per keyframe, not per frame). */
interface RevealPosition {
  version: number | null;
  keyframe: number;
}

declare global {
  interface Window {
    __CM_DEV_STATE__?: DevState;
  }
}

function App(): React.ReactElement {
  const {
    state,
    dispatch,
    handleMessage,
    startStroke,
    addPoint,
    endStroke,
    toggleDrawing,
    setPaused,
  } = useCanvas();

  const { accessToken, recoverSession, signOut } = useAuth();
  const [showDebug, setShowDebug] = useState(false);
  const { logMessage, ...debug } = useDebug({ token: showDebug ? accessToken : null });
  const apiUrl = getApiUrl();

  const agentStatus = deriveAgentStatus(state);
  const phase = deriveStudioPhase(agentStatus, getLastToolCall(state.messages));
  const isPaint = state.drawingStyle === 'paint';
  const versions = notebookVersions(state);

  // Refs for inline fetch validation
  const viewingPieceRef = useRef(state.viewingPiece);
  viewingPieceRef.current = state.viewingPiece;
  const pieceNumberRef = useRef(state.pieceNumber);
  pieceNumberRef.current = state.pieceNumber;
  const fetchAbortRef = useRef<AbortController | null>(null);
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;
  /** Direction of a New piece we started, recorded once the server confirms it. */
  const pendingPromptRef = useRef<string | null>(null);

  const onMessage = useCallback(
    (message: ServerMessage) => {
      if (message.type === 'agent_strokes_ready') {
        // Gallery guard
        if (viewingPieceRef.current !== null) return;

        // Stale piece guard
        if (message.piece_number < pieceNumberRef.current) return;

        // Piece sync
        if (message.piece_number > pieceNumberRef.current) {
          dispatch({ type: 'SET_PIECE_NUMBER', number: message.piece_number });
        }

        // Abort any in-flight fetch, start a new one
        fetchAbortRef.current?.abort();
        const controller = new AbortController();
        fetchAbortRef.current = controller;

        void fetchStrokesWithRetry({
          fetchFn: async () => {
            const token = accessTokenRef.current;
            if (!token) throw new Error('Missing access token');
            const response = await fetch(`${getApiUrl()}/strokes/pending`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) throw new Error('Failed to fetch strokes');
            const data = (await response.json()) as { strokes: PendingStroke[] };
            return data.strokes;
          },
          onSuccess: (strokes) => {
            dispatch({ type: 'ENQUEUE_STROKES', strokes });
          },
          onError: (error) => {
            console.error('[App] Failed to fetch strokes:', error);
          },
          signal: controller.signal,
        });

        logMessage(message);
        return;
      }
      handleMessage(message);
      if (message.type === 'new_canvas' && pendingPromptRef.current) {
        dispatch({ type: 'SET_PIECE_PROMPT', prompt: pendingPromptRef.current });
        pendingPromptRef.current = null;
      }
      logMessage(message);
    },
    [handleMessage, logMessage, dispatch]
  );

  // Cleanup fetch on unmount
  useEffect(
    () => (): void => {
      fetchAbortRef.current?.abort();
    },
    []
  );

  const { status: wsStatus, send } = useWebSocket({
    onMessage,
    token: accessToken,
    onAuthError: recoverSession,
  });

  // A prompt pending across a dropped connection can't be matched to a
  // server new_canvas any more; the next init carries the server's prompt.
  useEffect(() => {
    if (wsStatus !== 'connected') pendingPromptRef.current = null;
  }, [wsStatus]);

  // Callback when stroke animation completes
  const sendRef = useRef<((msg: { type: 'animation_done'; batch_id: number }) => void) | null>(
    null
  );
  const handleStrokesComplete = useCallback((batchId: number) => {
    sendRef.current?.({ type: 'animation_done', batch_id: batchId });
  }, []);

  // Program painting playback (paint mode). Progress fires per frame, so it
  // lives in a ref; only the keyframe position is state (changes per keyframe).
  const revealRef = useRef<RevealPlaybackInfo>(IDLE_REVEAL);
  const [revealPos, setRevealPos] = useState<RevealPosition>({ version: null, keyframe: -1 });
  const handlePaintingProgress = useCallback((info: RevealPlaybackInfo) => {
    revealRef.current = info;
    const version = info.playing ? info.version : null;
    const keyframe = info.playing ? info.keyframe : -1;
    setRevealPos((prev) =>
      prev.version === version && prev.keyframe === keyframe ? prev : { version, keyframe }
    );
    const dev = window.__CM_DEV_STATE__;
    if (import.meta.env.DEV && dev) {
      dev.revealKeyframe = info.keyframe;
      dev.revealOpsDone = info.opsDone;
      dev.revealPlaying = info.playing;
    }
  }, []);
  const handlePaintingPlaybackDone = useCallback(
    (assetBase: string) => dispatch({ type: 'PAINTING_PLAYBACK_DONE', assetBase }),
    [dispatch]
  );

  // Performance animation loop
  usePerformer({
    performance: state.performance,
    dispatch,
    paused: state.paused,
    inStudio: true, // Web app is always in studio mode
    onStrokesComplete: handleStrokesComplete,
  });

  // Optimistic pause/resume - update UI immediately, then notify server
  const handlePauseToggle = useCallback(() => {
    if (state.paused) {
      setPaused(false);
      send({ type: 'resume' });
    } else {
      setPaused(true);
      send({ type: 'pause' });
    }
  }, [state.paused, setPaused, send]);

  const [newPieceOpen, setNewPieceOpen] = useState(false);
  const closeNewPiece = useCallback(() => setNewPieceOpen(false), []);
  const handleStart = useCallback(
    (direction: string | undefined, style: DrawingStyleType, canvas: CanvasDimensions) => {
      setNewPieceOpen(false);
      dispatch({ type: 'SET_STYLE', drawingStyle: style, styleConfig: getStyleConfig(style) });
      setPaused(false);
      // Record the prompt only if the request actually went out; it is
      // applied when the server confirms with new_canvas.
      const sent = send({ type: 'new_canvas', direction, drawing_style: style, ...canvas });
      pendingPromptRef.current = sent ? (direction ?? null) : null;
      send({ type: 'resume' });
    },
    [dispatch, setPaused, send]
  );

  const handleNudge = useCallback(
    (text: string) => {
      send({ type: 'nudge', text });
      dispatch({ type: 'ADD_NUDGE', text });
    },
    [send, dispatch]
  );

  const handleClear = useCallback(() => send({ type: 'clear' }), [send]);

  // Keep sendRef in sync for stroke completion callback
  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  // Dev-only: expose render state so the visual-flow-test harness can tell
  // how far the client performance lags behind the server (painted strokes,
  // queued items, revealed monologue).
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    window.__CM_DEV_STATE__ = {
      strokesPainted: state.strokes.length,
      bufferLength: state.performance.buffer.length,
      revealedChars: state.performance.revealedText.length,
      paused: state.paused,
      pieceNumber: state.pieceNumber,
      paintingVersion: (state.painting.playing ?? state.painting.base)?.version ?? null,
      revealKeyframe: revealRef.current.keyframe,
      revealOpsDone: revealRef.current.opsDone,
      revealPlaying: revealRef.current.playing,
    };
  });

  const handleStrokeEnd = useCallback(() => {
    const path = endStroke();
    if (path) {
      send({ type: 'stroke', points: path.points });
    }
  }, [endStroke, send]);

  // ---- Versions, stage bar ------------------------------------------------

  const history = state.versionHistory.versions;
  const [viewingBase, setViewingBase] = useState<string | null>(null);
  // An older version stays selected only while it belongs to the piece on the easel.
  const viewed: PaintingVersionSummary | null =
    (viewingBase !== null && history.find((v) => v.asset_base === viewingBase)) || null;
  const live = state.painting.playing ?? state.painting.base;
  const shownBase = viewed?.asset_base ?? live?.asset_base ?? null;
  const manifest = useRevealManifest(apiUrl, isPaint ? shownBase : null);

  const segments = useMemo(() => {
    if (!isPaint || !shownBase) return [];
    const summary = history.find((v) => v.asset_base === shownBase);
    const stages = manifest
      ? stagesFromManifest(manifest)
      : stagesFromLabels(summary?.stages ?? []);
    const playing = !viewed && state.painting.playing !== null;
    const activeKeyframe = playing
      ? revealPos.version === state.painting.playing?.version
        ? Math.max(0, revealPos.keyframe)
        : 0
      : null;
    return buildStageBar(stages, activeKeyframe);
  }, [isPaint, shownBase, history, manifest, viewed, state.painting.playing, revealPos]);

  const title = pieceDisplayTitle({
    title: state.pieceTitle,
    prompt: state.piecePrompt,
    pieceNumber: state.pieceNumber,
  });
  const pillVersion =
    isPaint && phase === 'painting' ? (state.painting.playing?.version ?? versions.working) : null;
  const canSend = wsStatus === 'connected';

  const versionOverlay = viewed ? (
    <img
      className="canvas-version-view"
      src={paintingAssetUrl(apiUrl, viewed, PAINTING_FINAL_FILE)}
      alt={`Version ${viewed.version}`}
    />
  ) : null;

  return (
    <div className={`studio${showDebug ? ' with-debug' : ''}`}>
      <header className="studio-bar">
        <div className="studio-bar-left">
          <Link to="/" className="studio-home" aria-label="Code Monet home">
            <BrandMark size={24} />
          </Link>
          <span className="studio-divider" aria-hidden="true" />
          <h1 className="studio-title" title={title}>
            {title}
          </h1>
          <span className={`status-pill is-${phase}`} data-testid="status-pill">
            {isActivePhase(phase) && <span className="status-dot is-live" aria-hidden="true" />}
            {phase}
            {pillVersion !== null && ` v${pillVersion}`}
          </span>
          {wsStatus !== 'connected' && (
            <span className="studio-conn mono-label" role="status">
              {wsStatus === 'connecting' ? 'connecting…' : 'offline'}
            </span>
          )}
        </div>
        <div className="studio-bar-right">
          <button
            type="button"
            className="btn btn-ghost"
            data-testid="pause-button"
            onClick={handlePauseToggle}
            disabled={!canSend}
          >
            <Icon name={state.paused ? 'play' : 'pause'} />
            <span className="btn-label">{state.paused ? 'Resume' : 'Pause'}</span>
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            data-testid="start-button"
            onClick={() => setNewPieceOpen(true)}
            disabled={!canSend}
          >
            <Icon name="plus" />
            <span className="btn-label">New piece</span>
          </button>
          <StudioMenu
            drawingEnabled={state.drawingEnabled}
            onToggleDrawing={toggleDrawing}
            onClear={handleClear}
            debugVisible={showDebug}
            onToggleDebug={() => setShowDebug((v) => !v)}
            onSignOut={signOut}
          />
        </div>
      </header>

      <main className="studio-body">
        <section className="studio-stage" aria-label="Canvas">
          <div
            className="studio-canvas"
            style={
              {
                '--canvas-aspect': `${state.canvasWidth} / ${state.canvasHeight}`,
              } as React.CSSProperties
            }
          >
            <Canvas
              strokes={state.strokes}
              currentStroke={state.currentStroke}
              agentStroke={state.performance.agentStroke}
              agentStrokeStyle={state.performance.agentStrokeStyle}
              penPosition={state.performance.penPosition}
              penDown={state.performance.penDown}
              // Drawing over an older version's image would land on the live canvas.
              drawingEnabled={state.drawingEnabled && viewed === null}
              canvasWidth={state.canvasWidth}
              canvasHeight={state.canvasHeight}
              styleConfig={state.styleConfig}
              showIdleAnimation={shouldShowIdleAnimation(state)}
              painting={state.painting}
              apiUrl={apiUrl}
              onPaintingPlaybackDone={handlePaintingPlaybackDone}
              onPaintingProgress={handlePaintingProgress}
              overlay={versionOverlay}
              onStrokeStart={startStroke}
              onStrokeMove={addPoint}
              onStrokeEnd={handleStrokeEnd}
            />
          </div>
          <div className="studio-under">
            {isPaint ? (
              <>
                <StageBar segments={segments} />
                <div className="studio-versions-row">
                  <VersionChips
                    versions={history}
                    viewing={viewed?.asset_base ?? null}
                    onSelect={(v) => setViewingBase(v?.asset_base ?? null)}
                  />
                  {viewed && (
                    <button
                      type="button"
                      className="btn-link back-to-live"
                      onClick={() => setViewingBase(null)}
                    >
                      Back to live <Icon name="arrow" />
                    </button>
                  )}
                </div>
              </>
            ) : (
              <p className="mono-label">
                plotter · {state.strokes.length.toLocaleString()} strokes
              </p>
            )}
          </div>
        </section>

        <Notebook
          entries={state.notebook}
          phase={phase}
          latestVersion={versions.latest}
          canSend={canSend}
          onNudge={handleNudge}
        />

        {showDebug && (
          <div className="studio-debug">
            <DebugPanel
              agent={debug.agent}
              files={debug.files}
              messageLog={debug.messageLog}
              onRefresh={debug.refresh}
              onClearLog={debug.clearLog}
            />
          </div>
        )}
      </main>

      {newPieceOpen && (
        <NewPieceDialog
          initialStyle={state.drawingStyle}
          onCancel={closeNewPiece}
          onStart={handleStart}
        />
      )}
    </div>
  );
}

export default App;
