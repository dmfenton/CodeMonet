/**
 * Drawing Agent Web App - Studio View
 */

import React, { useCallback, useEffect, useRef } from 'react';
import type { DrawingStyleType, PendingStroke, ServerMessage } from '@code-monet/shared';
import {
  deriveAgentStatus,
  fetchStrokesWithRetry,
  getStyleConfig,
  shouldShowIdleAnimation,
  STATUS_LABELS,
  useCanvas,
  usePerformer,
} from '@code-monet/shared';
import { getApiUrl } from './config';

import { Canvas } from './components/Canvas';
import { MessageStream } from './components/MessageStream';
import { DebugPanel } from './components/DebugPanel';
import { ActionBar } from './components/ActionBar';
import { StatusOverlay } from './components/StatusOverlay';
import { useWebSocket } from './hooks/useWebSocket';
import { useDebug } from './hooks/useDebug';
import { useAuth } from './context/AuthContext';

function App(): React.ReactElement {
  const { state, dispatch, handleMessage, startStroke, addPoint, endStroke, toggleDrawing, setPaused } =
    useCanvas();

  const { accessToken } = useAuth();
  const { logMessage, ...debug } = useDebug({ token: accessToken });

  // Derive status from messages
  const agentStatus = deriveAgentStatus(state);

  // Refs for inline fetch validation
  const viewingPieceRef = useRef(state.viewingPiece);
  viewingPieceRef.current = state.viewingPiece;
  const pieceNumberRef = useRef(state.pieceNumber);
  pieceNumberRef.current = state.pieceNumber;
  const fetchAbortRef = useRef<AbortController | null>(null);
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;

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

        // Don't pass to reducer (no longer handled there)
        logMessage(message);
        return;
      }
      handleMessage(message);
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

  const { status: wsStatus, send } = useWebSocket({ onMessage, token: accessToken });

  // Callback when stroke animation completes
  const sendRef = useRef<((msg: { type: 'animation_done'; batch_id: number }) => void) | null>(
    null
  );
  const handleStrokesComplete = useCallback((batchId: number) => {
    sendRef.current?.({ type: 'animation_done', batch_id: batchId });
  }, []);

  // Performance animation loop
  usePerformer({
    performance: state.performance,
    dispatch,
    paused: state.paused,
    inStudio: true, // Web app is always in studio mode
    onStrokesComplete: handleStrokesComplete,
  });

  // Optimistic pause/resume handlers - update UI immediately, then notify server
  const handlePause = useCallback(() => {
    setPaused(true);
    send({ type: 'pause' });
  }, [setPaused, send]);

  const handleStart = useCallback((direction?: string) => {
    setPaused(false);
    send({ type: 'new_canvas', direction, drawing_style: state.drawingStyle });
    send({ type: 'resume' });
  }, [setPaused, send, state.drawingStyle]);

  const handleNewCanvas = useCallback(() => {
    send({ type: 'new_canvas', drawing_style: state.drawingStyle });
  }, [send, state.drawingStyle]);

  const handleStyleChange = useCallback((style: DrawingStyleType) => {
    dispatch({
      type: 'SET_STYLE',
      drawingStyle: style,
      styleConfig: getStyleConfig(style),
    });
  }, [dispatch]);

  // Keep sendRef in sync for stroke completion callback
  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  const handleStrokeEnd = useCallback(() => {
    const path = endStroke();
    if (path) {
      send({ type: 'stroke', points: path.points });
    }
  }, [endStroke, send]);

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1>Drawing Agent</h1>
          <div className="connection-status">
            <div className={`connection-dot ${wsStatus}`} />
          </div>
        </div>
        <div className="header-center">
          <div className={`status-pill ${agentStatus}`}>{STATUS_LABELS[agentStatus]}</div>
        </div>
        <div className="header-right">
          <span className="piece-count">Piece #{state.pieceNumber}</span>
        </div>
      </header>

      <ActionBar
        paused={state.paused}
        drawingEnabled={state.drawingEnabled}
        drawingStyle={state.drawingStyle}
        onSend={send}
        onStyleChange={handleStyleChange}
        onToggleDrawing={toggleDrawing}
        onPause={handlePause}
        onStart={handleStart}
        onNewCanvas={handleNewCanvas}
      />

      <div className="thinking-strip">
        <StatusOverlay status={agentStatus} performance={state.performance} messages={state.messages} />
      </div>

      <div className="canvas-container">
        <Canvas
          strokes={state.strokes}
          currentStroke={state.currentStroke}
          agentStroke={state.performance.agentStroke}
          agentStrokeStyle={state.performance.agentStrokeStyle}
          penPosition={state.performance.penPosition}
          penDown={state.performance.penDown}
          drawingEnabled={state.drawingEnabled}
          styleConfig={state.styleConfig}
          showIdleAnimation={shouldShowIdleAnimation(state)}
          onStrokeStart={startStroke}
          onStrokeMove={addPoint}
          onStrokeEnd={handleStrokeEnd}
        />
      </div>

      <div className="right-panel">
        <MessageStream messages={state.messages} />
        <DebugPanel
          agent={debug.agent}
          files={debug.files}
          messageLog={debug.messageLog}
          onRefresh={debug.refresh}
          onClearLog={debug.clearLog}
        />
      </div>
    </div>
  );
}

export default App;
