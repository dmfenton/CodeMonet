/**
 * StatusOverlay - Shows agent status in a fixed position above the canvas.
 *
 * Modes:
 * - Thinking: Bionic reading display from performance.revealedText
 * - Executing: "Running [tool_name]..." with spinner
 * - Drawing: "Drawing..." with animated indicator
 * - Idle/Paused: Subtle indicator
 */

import React, { useMemo } from 'react';
import type { AgentMessage, AgentStatus, PerformanceState } from '@code-monet/shared';
import {
  getLastToolCall,
  splitWords,
  TOOL_DISPLAY_NAMES,
} from '@code-monet/shared';

interface StatusOverlayProps {
  status: AgentStatus;
  performance: PerformanceState;
  messages: AgentMessage[];
  /** Program painting: label of the keyframe being revealed ('' when none). */
  stageLabel?: string;
}

/**
 * Render a word (bionic reading disabled - renders as plain text).
 */
function BionicWord({ word }: { word: string }): React.ReactElement {
  return <span className="bionic-word">{word}</span>;
}

/**
 * Thinking display with bionic reading.
 * Uses performance.revealedText which is already progressively revealed by usePerformer.
 */
function ThinkingDisplay({
  performance,
}: {
  performance: PerformanceState;
}): React.ReactElement {
  // Get revealed text from performance state (already progressively revealed)
  const displayedWords = useMemo(
    () => splitWords(performance.revealedText),
    [performance.revealedText]
  );

  // Check if there are more words to reveal
  const isBuffering = useMemo(() => {
    const hasWordsInBuffer = performance.buffer.some((item) => item.type === 'words');
    if (performance.onStage?.type === 'words') {
      const totalWords = splitWords(performance.onStage.text).length;
      if (performance.wordIndex < totalWords) return true;
    }
    return hasWordsInBuffer;
  }, [performance.buffer, performance.onStage, performance.wordIndex]);

  if (displayedWords.length === 0) {
    return <span className="status-text">Thinking...</span>;
  }

  return (
    <div className="thinking-display">
      {displayedWords.map((word, i) => (
        <React.Fragment key={`${i}-${word}`}>
          <BionicWord word={word} />
          {i < displayedWords.length - 1 && ' '}
        </React.Fragment>
      ))}
      {isBuffering && <span className="cursor"> ▍</span>}
    </div>
  );
}

export function StatusOverlay({
  status,
  performance,
  messages,
  stageLabel = '',
}: StatusOverlayProps): React.ReactElement | null {
  const lastTool = getLastToolCall(messages);

  // Check if there's any revealed text
  const hasContent = performance.revealedText.length > 0 || performance.buffer.length > 0;

  // Show status indicator for non-thinking active states
  const renderStatusBadge = (): React.ReactElement | null => {
    switch (status) {
      case 'executing': {
        const toolLabel = lastTool ? TOOL_DISPLAY_NAMES[lastTool] : 'executing';
        return (
          <div className="status-badge executing">
            <span className="spinner" />
            <span>{toolLabel}</span>
          </div>
        );
      }
      case 'drawing':
        return (
          <div className="status-badge drawing">
            <span className="drawing-icon">✏</span>
            <span>{stageLabel ? `Painting · ${stageLabel}` : 'Drawing'}</span>
          </div>
        );
      default:
        return null;
    }
  };

  // Active states that should show thinking (if available) + status badge
  const isActiveState = status === 'thinking' || status === 'executing' || status === 'drawing';

  if (!isActiveState) {
    // Paused, idle, error - show simple status
    if (status === 'paused') {
      return (
        <div className="status-overlay">
          <div className="paused-display">
            <span className="status-text muted">Paused</span>
          </div>
        </div>
      );
    }
    if (status === 'error') {
      return (
        <div className="status-overlay">
          <div className="error-display">
            <span className="status-text error">Error</span>
          </div>
        </div>
      );
    }
    return null; // idle
  }

  // Active state: show thinking text (if any) with status badge
  const statusBadge = renderStatusBadge();

  return (
    <div className="status-overlay">
      {hasContent ? (
        <ThinkingDisplay performance={performance} />
      ) : (
        <span className="status-text">Thinking...</span>
      )}
      {statusBadge}
    </div>
  );
}
