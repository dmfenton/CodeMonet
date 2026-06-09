/**
 * StudioScreen - Canvas view with controls.
 * Encapsulates Canvas, LiveStatus, MessageStream, and ActionBar.
 */

import React, { useCallback } from 'react';
import { StyleSheet, View } from 'react-native';

import type { AgentStatus, CanvasHookState, ToolName } from '@code-monet/shared';
import { shouldShowIdleAnimation } from '@code-monet/shared';

import { ActionBar, Canvas, LiveStatus, MessageStream } from '../components';
import type { StudioAction } from '../context';

/** Props for StudioScreen */
export interface StudioScreenProps {
  /** Canvas state from context */
  canvasState: CanvasHookState;
  /** Current agent status */
  agentStatus: AgentStatus;
  /** Current tool being used */
  currentTool: ToolName | null;
  /** WebSocket connected state */
  wsConnected: boolean;
  /** Gallery count for action bar */
  galleryCount: number;
  /** Whether viewing a completed gallery piece (read-only) */
  viewingPiece: number | null;
  /** Callback when action is triggered */
  onAction: (action: StudioAction) => void;
  /** Callback for stroke start */
  onStrokeStart: (x: number, y: number) => void;
  /** Callback for stroke move */
  onStrokeMove: (x: number, y: number) => void;
  /** Callback for stroke end */
  onStrokeEnd: () => void;
}

export function StudioScreen({
  canvasState,
  agentStatus,
  currentTool,
  wsConnected,
  galleryCount,
  viewingPiece,
  onAction,
  onStrokeStart,
  onStrokeMove,
  onStrokeEnd,
}: StudioScreenProps): React.JSX.Element {
  const isViewOnly = viewingPiece !== null;
  // Action bar callbacks
  const handleDrawToggle = useCallback(() => {
    onAction({ type: 'draw_toggle' });
  }, [onAction]);

  const handleNudge = useCallback(() => {
    onAction({ type: 'nudge' });
  }, [onAction]);

  const handlePauseToggle = useCallback(() => {
    onAction({ type: 'pause_toggle' });
  }, [onAction]);

  const handleHome = useCallback(() => {
    onAction({ type: 'home' });
  }, [onAction]);

  const handleGallery = useCallback(() => {
    onAction({ type: 'gallery' });
  }, [onAction]);

  return (
    <>
      {/* Live Status - Above canvas for visibility (hidden when viewing completed piece) */}
      {!isViewOnly && (
        <LiveStatus
          performance={canvasState.performance}
          status={agentStatus}
          currentTool={currentTool}
        />
      )}

      {/* Canvas - Main area */}
      <View style={styles.canvasContainer}>
        <Canvas
          strokes={canvasState.strokes}
          currentStroke={canvasState.currentStroke}
          agentStroke={canvasState.performance.agentStroke}
          agentStrokeStyle={canvasState.performance.agentStrokeStyle}
          penPosition={canvasState.performance.penPosition}
          penDown={canvasState.performance.penDown}
          drawingEnabled={!isViewOnly && canvasState.drawingEnabled}
          canvasWidth={canvasState.canvasWidth}
          canvasHeight={canvasState.canvasHeight}
          styleConfig={canvasState.styleConfig}
          showIdleAnimation={!isViewOnly && shouldShowIdleAnimation(canvasState)}
          onStrokeStart={onStrokeStart}
          onStrokeMove={onStrokeMove}
          onStrokeEnd={onStrokeEnd}
        />
      </View>

      {/* Message History - Collapsible (hidden when viewing completed piece) */}
      {!isViewOnly && <MessageStream messages={canvasState.messages} />}

      {/* Action Bar - Bottom */}
      <ActionBar
        drawingEnabled={canvasState.drawingEnabled}
        paused={canvasState.paused}
        connected={wsConnected}
        galleryCount={galleryCount}
        viewOnly={isViewOnly}
        onDrawToggle={handleDrawToggle}
        onNudge={handleNudge}
        onPauseToggle={handlePauseToggle}
        onNewCanvas={handleHome}
        onGallery={handleGallery}
      />
    </>
  );
}

const styles = StyleSheet.create({
  canvasContainer: {
    flex: 1,
    justifyContent: 'center',
  },
});
