/**
 * Studio phase: what the status pill says (painting / thinking / critique /
 * paused / idle / error), refined from AgentStatus by the tool in flight.
 */

import type { AgentStatus, ToolName } from '../types';

export type StudioPhase = 'painting' | 'thinking' | 'critique' | 'paused' | 'idle' | 'error';

export const STUDIO_PHASE_LABELS: Record<StudioPhase, string> = {
  painting: 'painting',
  thinking: 'thinking',
  critique: 'critique',
  paused: 'paused',
  idle: 'idle',
  error: 'error',
};

const PAINTING_TOOLS: ReadonlySet<string> = new Set(['paint', 'draw_paths', 'generate_svg']);

export function deriveStudioPhase(status: AgentStatus, lastTool: ToolName | null): StudioPhase {
  switch (status) {
    case 'paused':
      return 'paused';
    case 'error':
      return 'error';
    case 'idle':
      return 'idle';
    case 'drawing':
      return 'painting';
    case 'thinking':
      return 'thinking';
    case 'executing':
      if (lastTool === 'critique_canvas') return 'critique';
      if (lastTool !== null && PAINTING_TOOLS.has(lastTool)) return 'painting';
      return 'thinking';
  }
}

/** Phases that show the emphasis dot. */
export const isActivePhase = (phase: StudioPhase): boolean =>
  phase === 'painting' || phase === 'thinking' || phase === 'critique';
