/**
 * Shared hook for LiveStatus / StatusOverlay display logic.
 *
 * Returns a discriminated union describing what to render.
 * Platform-specific components (React Native / web) use this
 * to render with their own primitives while sharing identical logic.
 */

import { useMemo } from 'react';

import type { AgentStatus, ToolName } from '../types';
import { TOOL_DISPLAY_NAMES } from '../types';
import type { PerformanceState } from '../canvas/reducer';
import { splitWords } from '../utils';

// ---------------------------------------------------------------------------
// Display mode types
// ---------------------------------------------------------------------------

export interface EventDisplay {
  type: 'event';
  /** The event text, e.g. "Drawing 3 paths..." or "Drew 3 paths" */
  text: string;
  /** Tool name for icon/color lookup (e.g. 'draw_paths') */
  toolName: ToolName | 'unknown';
  /** Whether the event is still in progress */
  isInProgress: boolean;
}

export interface ThinkingDisplay {
  type: 'thinking';
  /** Words revealed so far */
  words: string[];
  /** Whether more words are buffered */
  isBuffering: boolean;
}

export interface ActiveDisplay {
  type: 'active';
  /** Human-readable label, e.g. "Thinking", "drawing paths" */
  label: string;
}

export interface InactiveDisplay {
  type: 'inactive';
  /** 'paused' or 'error' */
  statusType: 'paused' | 'error';
  /** Human-readable label */
  label: string;
}

export interface HiddenDisplay {
  type: 'hidden';
}

export type LiveStatusDisplay =
  | EventDisplay
  | ThinkingDisplay
  | ActiveDisplay
  | InactiveDisplay
  | HiddenDisplay;

// ---------------------------------------------------------------------------
// Status label helper (exported for tests)
// ---------------------------------------------------------------------------

export function getStatusLabel(status: AgentStatus, currentTool?: ToolName | null): string {
  if (status === 'executing' && currentTool) {
    return TOOL_DISPLAY_NAMES[currentTool] ?? 'Running code';
  }

  switch (status) {
    case 'thinking':
      return 'Thinking';
    case 'drawing':
      return 'Drawing';
    case 'executing':
      return 'Running code';
    case 'paused':
      return 'Paused';
    case 'error':
      return 'Error';
    default:
      return '';
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useLiveStatus(
  performance: PerformanceState,
  status: AgentStatus,
  currentTool?: ToolName | null,
): LiveStatusDisplay {
  const eventDisplay = useMemo((): EventDisplay | null => {
    if (performance.onStage?.type !== 'event') return null;
    const message = performance.onStage.message;
    const toolName: ToolName | 'unknown' =
      (message.metadata?.tool_name as ToolName | undefined) ?? 'unknown';
    const isInProgress = message.status === 'started';
    return { type: 'event', text: message.text, toolName, isInProgress };
  }, [performance.onStage]);

  const displayedWords = useMemo(
    () => splitWords(performance.revealedText),
    [performance.revealedText],
  );

  const isBuffering = useMemo(() => {
    const hasWordsInBuffer = performance.buffer.some((item) => item.type === 'words');
    if (performance.onStage?.type === 'words') {
      const totalWords = splitWords(performance.onStage.text).length;
      if (performance.wordIndex < totalWords) return true;
    }
    return hasWordsInBuffer;
  }, [performance.buffer, performance.onStage, performance.wordIndex]);

  return useMemo((): LiveStatusDisplay => {
    const hasContent =
      displayedWords.length > 0 || performance.buffer.length > 0 || eventDisplay !== null;

    // Idle with nothing to show
    if (status === 'idle' && !hasContent) {
      return { type: 'hidden' };
    }

    // Event on stage takes priority
    if (eventDisplay) {
      return eventDisplay;
    }

    // Thinking text
    if (displayedWords.length > 0) {
      return { type: 'thinking', words: displayedWords, isBuffering };
    }

    const isActive = status === 'thinking' || status === 'drawing' || status === 'executing';

    // Active but no content yet
    if (isActive) {
      return { type: 'active', label: getStatusLabel(status, currentTool) };
    }

    // Paused / error
    if (status === 'paused') {
      return { type: 'inactive', statusType: 'paused', label: 'Paused' };
    }
    if (status === 'error') {
      return { type: 'inactive', statusType: 'error', label: 'Error' };
    }

    return { type: 'hidden' };
  }, [eventDisplay, displayedWords, isBuffering, performance.buffer.length, status, currentTool]);
}
