/**
 * StatusOverlay - Shows agent status above the canvas.
 *
 * Uses the same shared useLiveStatus hook as the mobile LiveStatus
 * component, rendering with HTML/CSS instead of React Native primitives.
 *
 * Display modes:
 * - Events: Tool icon + action text as a single activity row
 * - Thinking: Streaming text with cursor (no header)
 * - Active with no content: Pulsing dot + status label
 * - Paused/Error: Icon + label
 */

import React from 'react';
import type { AgentMessage, AgentStatus, PerformanceState, ToolName } from '@code-monet/shared';
import { getLastToolCall, useLiveStatus } from '@code-monet/shared';

interface StatusOverlayProps {
  status: AgentStatus;
  performance: PerformanceState;
  messages: AgentMessage[];
}

// Tool-specific symbols for web (matches mobile Ionicons)
const TOOL_SYMBOLS: Record<string, string> = {
  draw_paths: '🖌',
  generate_svg: '⟨/⟩',
  view_canvas: '◎',
  mark_piece_done: '✓',
  imagine: '✧',
  sign_canvas: '✍',
  name_piece: 'Aa',
  unknown: '◦',
};

// Tool-specific CSS colors (matches mobile getToolBorderColor)
const TOOL_COLORS: Record<string, string> = {
  draw_paths: 'var(--atelier-indigo)',
  generate_svg: 'var(--atelier-lavender)',
  view_canvas: 'var(--text-muted)',
  mark_piece_done: 'var(--atelier-sage)',
  imagine: 'var(--atelier-ochre)',
  sign_canvas: 'var(--atelier-indigo)',
  name_piece: 'var(--atelier-indigo)',
  unknown: 'var(--atelier-indigo)',
};

export function StatusOverlay({
  status,
  performance,
  messages,
}: StatusOverlayProps): React.ReactElement | null {
  // Derive currentTool from messages (same as mobile StudioContext)
  const currentTool: ToolName | null = getLastToolCall(messages);
  const display = useLiveStatus(performance, status, currentTool);

  if (display.type === 'hidden') {
    return null;
  }

  // Event on stage -> tool symbol + action text
  if (display.type === 'event') {
    const symbol = TOOL_SYMBOLS[display.toolName] ?? TOOL_SYMBOLS.unknown;
    const toolColor = TOOL_COLORS[display.toolName] ?? TOOL_COLORS.unknown;

    return (
      <div className="status-overlay">
        <div className={`activity-row ${display.isInProgress ? 'in-progress' : 'completed'}`}>
          <span
            className={`activity-icon ${display.isInProgress ? 'pulse' : ''}`}
            style={{ color: display.isInProgress ? toolColor : 'var(--text-muted)' }}
          >
            {symbol}
          </span>
          <span
            className="activity-text"
            style={{ color: display.isInProgress ? 'var(--text-primary)' : 'var(--text-muted)' }}
          >
            {display.text}
          </span>
        </div>
      </div>
    );
  }

  // Thinking text -> show text directly, no header
  if (display.type === 'thinking') {
    return (
      <div className="status-overlay">
        <div className="thinking-display">
          {display.words.map((word, i) => (
            <React.Fragment key={`${i}-${word}`}>
              <span className="bionic-word">{word}</span>
              {i < display.words.length - 1 && ' '}
            </React.Fragment>
          ))}
          {display.isBuffering && <span className="cursor"> ▍</span>}
        </div>
      </div>
    );
  }

  // Active but no content yet -> pulsing dot + label
  if (display.type === 'active') {
    return (
      <div className="status-overlay">
        <div className="activity-row in-progress">
          <span className="activity-dot pulse" />
          <span className="activity-label">{display.label}...</span>
        </div>
      </div>
    );
  }

  // Paused / Error -> icon + label
  if (display.type === 'inactive') {
    const icon = display.statusType === 'error' ? '⚠' : '⏸';
    return (
      <div className="status-overlay">
        <div className="activity-row">
          <span className={`activity-icon ${display.statusType}`}>{icon}</span>
          <span className={`activity-label ${display.statusType}`}>{display.label}</span>
        </div>
      </div>
    );
  }

  return null;
}
