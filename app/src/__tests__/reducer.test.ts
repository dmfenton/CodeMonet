/**
 * Tests for canvas reducer functions.
 */

import {
  canvasReducer,
  deriveAgentStatus,
  hasInProgressEvents,
  initialState,
  initialPerformanceState,
  shouldShowIdleAnimation,
  type CanvasHookState,
} from '@code-monet/shared';
import type { AgentMessage } from '@code-monet/shared';

describe('hasInProgressEvents', () => {
  it('returns false for empty messages', () => {
    expect(hasInProgressEvents([])).toBe(false);
  });

  it('returns false when only thinking messages exist (thinking does not block)', () => {
    // NOTE: hasInProgressEvents only blocks on code_execution, not thinking
    // Thinking text is now in state.thinking, not messages. Archived thinking also doesn't block.
    const messages: AgentMessage[] = [
      { id: 'thinking_123', type: 'thinking', text: 'Archived thinking...', timestamp: Date.now() },
    ];
    expect(hasInProgressEvents(messages)).toBe(false);
  });

  it('returns false for finalized thinking message', () => {
    const messages: AgentMessage[] = [
      { id: 'thinking_123', type: 'thinking', text: 'Done thinking', timestamp: Date.now() },
    ];
    expect(hasInProgressEvents(messages)).toBe(false);
  });

  it('returns true for code_execution with status started', () => {
    const messages: AgentMessage[] = [
      {
        id: 'exec_1',
        type: 'code_execution',
        text: 'Running tool',
        timestamp: Date.now(),
        status: 'started',
        metadata: { tool_name: 'draw_paths' },
      },
    ];
    expect(hasInProgressEvents(messages)).toBe(true);
  });

  it('returns false for code_execution with return_code', () => {
    const messages: AgentMessage[] = [
      {
        id: 'exec_1',
        type: 'code_execution',
        text: 'Tool completed',
        timestamp: Date.now(),
        metadata: { tool_name: 'draw_paths', return_code: 0 },
      },
    ];
    expect(hasInProgressEvents(messages)).toBe(false);
  });

  it('returns true if any message is in-progress among multiple', () => {
    const messages: AgentMessage[] = [
      { id: 'thinking_1', type: 'thinking', text: 'First thought', timestamp: Date.now() },
      {
        id: 'exec_1',
        type: 'code_execution',
        text: 'Running',
        timestamp: Date.now(),
        status: 'started',
        metadata: { tool_name: 'draw_paths' },
      },
    ];
    expect(hasInProgressEvents(messages)).toBe(true);
  });

  it('returns false when all events are completed', () => {
    const messages: AgentMessage[] = [
      { id: 'thinking_1', type: 'thinking', text: 'First thought', timestamp: Date.now() },
      {
        id: 'exec_1',
        type: 'code_execution',
        text: 'Done',
        timestamp: Date.now(),
        metadata: { tool_name: 'draw_paths', return_code: 0 },
      },
    ];
    expect(hasInProgressEvents(messages)).toBe(false);
  });

  it('returns false when started and completed messages both exist for same tool', () => {
    // This is the real-world case: both "started" and "completed" messages exist
    const messages: AgentMessage[] = [
      {
        id: 'exec_started',
        type: 'code_execution',
        text: 'Drawing 3 paths...',
        timestamp: Date.now(),
        iteration: 1,
        metadata: { tool_name: 'draw_paths' }, // No return_code
      },
      {
        id: 'exec_completed',
        type: 'code_execution',
        text: 'Drew 3 paths',
        timestamp: Date.now(),
        iteration: 1,
        metadata: { tool_name: 'draw_paths', return_code: 0 },
      },
    ];
    expect(hasInProgressEvents(messages)).toBe(false);
  });

  it('returns true when started exists but completed is for different iteration', () => {
    const messages: AgentMessage[] = [
      {
        id: 'exec_started',
        type: 'code_execution',
        text: 'Drawing...',
        timestamp: Date.now(),
        iteration: 2, // Different iteration
        status: 'started',
        metadata: { tool_name: 'draw_paths' },
      },
      {
        id: 'exec_completed',
        type: 'code_execution',
        text: 'Drew paths',
        timestamp: Date.now(),
        iteration: 1, // Completed is for iteration 1
        status: 'completed',
        metadata: { tool_name: 'draw_paths', return_code: 0 },
      },
    ];
    expect(hasInProgressEvents(messages)).toBe(true);
  });
});

describe('deriveAgentStatus', () => {
  const baseState: CanvasHookState = {
    ...initialState,
    paused: false,
  };

  it('returns paused when paused is true', () => {
    const state = { ...baseState, paused: true };
    expect(deriveAgentStatus(state)).toBe('paused');
  });

  it('returns error when last message is error', () => {
    const state: CanvasHookState = {
      ...baseState,
      messages: [{ id: 'err_1', type: 'error', text: 'Something failed', timestamp: Date.now() }],
    };
    expect(deriveAgentStatus(state)).toBe('error');
  });

  it('returns idle when only thinking text exists (no words on stage/buffer)', () => {
    const state: CanvasHookState = {
      ...baseState,
      thinking: 'I am currently thinking about this...',
    };
    // state.thinking is for archiving only — status is driven by performance model
    expect(deriveAgentStatus(state)).toBe('idle');
  });

  it('returns executing when code_execution is in-progress', () => {
    const state: CanvasHookState = {
      ...baseState,
      messages: [
        {
          id: 'exec_1',
          type: 'code_execution',
          text: 'Running',
          timestamp: Date.now(),
          status: 'started',
          metadata: { tool_name: 'draw_paths' },
        },
      ],
    };
    expect(deriveAgentStatus(state)).toBe('executing');
  });

  it('returns drawing when strokes in performance buffer', () => {
    const state: CanvasHookState = {
      ...baseState,
      performance: {
        ...baseState.performance,
        buffer: [{ type: 'strokes', strokes: [], id: 'perf_1' }],
      },
    };
    expect(deriveAgentStatus(state)).toBe('drawing');
  });

  it('returns idle when no active state', () => {
    expect(deriveAgentStatus(baseState)).toBe('idle');
  });

  it('prioritizes paused over everything', () => {
    const state: CanvasHookState = {
      ...baseState,
      paused: true,
      thinking: 'I am thinking...',
      performance: {
        ...baseState.performance,
        buffer: [{ type: 'strokes', strokes: [], id: 'perf_1' }],
      },
    };
    expect(deriveAgentStatus(state)).toBe('paused');
  });

  it('prioritizes error over thinking', () => {
    const state: CanvasHookState = {
      ...baseState,
      thinking: 'I am thinking...',
      messages: [{ id: 'err_1', type: 'error', text: 'Failed', timestamp: Date.now() }],
    };
    expect(deriveAgentStatus(state)).toBe('error');
  });
});

describe('shouldShowIdleAnimation', () => {
  const baseState: CanvasHookState = {
    ...initialState,
    paused: false,
  };

  it('returns true when canvas empty and not drawing', () => {
    expect(shouldShowIdleAnimation(baseState)).toBe(true);
  });

  it('returns false when canvas has strokes', () => {
    const state: CanvasHookState = {
      ...baseState,
      strokes: [{ type: 'polyline', points: [{ x: 0, y: 0 }] }],
    };
    expect(shouldShowIdleAnimation(state)).toBe(false);
  });

  it('returns false when user is drawing (currentStroke has points)', () => {
    const state: CanvasHookState = {
      ...baseState,
      currentStroke: [{ x: 10, y: 10 }],
    };
    expect(shouldShowIdleAnimation(state)).toBe(false);
  });

  it('returns false when agent is drawing (agentStroke has points)', () => {
    const state: CanvasHookState = {
      ...baseState,
      performance: {
        ...baseState.performance,
        agentStroke: [{ x: 10, y: 10 }],
      },
    };
    expect(shouldShowIdleAnimation(state)).toBe(false);
  });
});

describe('initialPerformanceState', () => {
  it('includes travelTarget as null', () => {
    expect(initialPerformanceState.travelTarget).toBeNull();
  });
});

describe('PEN_TRAVEL_BATCH', () => {
  it('updates penPosition and sets penDown to false', () => {
    const state: CanvasHookState = {
      ...initialState,
      performance: {
        ...initialState.performance,
        penPosition: { x: 0, y: 0 },
        penDown: true,
      },
    };

    const result = canvasReducer(state, {
      type: 'PEN_TRAVEL_BATCH',
      points: [{ x: 50, y: 50 }, { x: 100, y: 100 }],
    });

    expect(result.performance.penPosition).toEqual({ x: 100, y: 100 });
    expect(result.performance.penDown).toBe(false);
  });

  it('returns unchanged state for empty points', () => {
    const state: CanvasHookState = {
      ...initialState,
      performance: {
        ...initialState.performance,
        penPosition: { x: 10, y: 10 },
      },
    };

    const result = canvasReducer(state, { type: 'PEN_TRAVEL_BATCH', points: [] });
    expect(result).toBe(state);
  });
});

describe('PEN_TRAVEL_COMPLETE', () => {
  it('clears travelTarget', () => {
    const state: CanvasHookState = {
      ...initialState,
      performance: {
        ...initialState.performance,
        travelTarget: { x: 100, y: 100 },
      },
    };

    const result = canvasReducer(state, { type: 'PEN_TRAVEL_COMPLETE' });
    expect(result.performance.travelTarget).toBeNull();
  });
});

describe('STROKE_COMPLETE with travelTarget', () => {
  it('sets travelTarget to next stroke first point', () => {
    const state: CanvasHookState = {
      ...initialState,
      performance: {
        ...initialState.performance,
        onStage: {
          type: 'strokes',
          strokes: [
            {
              batch_id: 0,
              path: { type: 'polyline', points: [{ x: 0, y: 0 }, { x: 10, y: 10 }] },
              points: [{ x: 0, y: 0 }, { x: 10, y: 10 }],
            },
            {
              batch_id: 0,
              path: { type: 'polyline', points: [{ x: 50, y: 50 }, { x: 60, y: 60 }] },
              points: [{ x: 50, y: 50 }, { x: 60, y: 60 }],
            },
          ],
          id: 'test-1',
        },
        strokeIndex: 0,
      },
    };

    const result = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    expect(result.performance.travelTarget).toEqual({ x: 50, y: 50 });
  });

  it('sets travelTarget to null when no next stroke', () => {
    const state: CanvasHookState = {
      ...initialState,
      performance: {
        ...initialState.performance,
        onStage: {
          type: 'strokes',
          strokes: [
            {
              batch_id: 0,
              path: { type: 'polyline', points: [{ x: 0, y: 0 }] },
              points: [{ x: 0, y: 0 }],
            },
          ],
          id: 'test-1',
        },
        strokeIndex: 0,
      },
    };

    const result = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    expect(result.performance.travelTarget).toBeNull();
  });
});

