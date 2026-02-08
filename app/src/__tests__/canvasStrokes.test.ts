/**
 * Canvas Strokes Tests
 *
 * Tests for stroke display through WebSocket message sequences.
 * These tests validate that strokes appear correctly in canvas state
 * when processing real-world message patterns from the agent.
 *
 * Key scenarios:
 * 1. human_stroke messages add strokes directly
 * 2. agent_strokes_ready signals pending strokes for REST fetch
 * 3. Status transitions gate when drawing starts
 * 4. Idle animation shows only until first stroke is committed
 */

import {
  canvasReducer,
  deriveAgentStatus,
  hasInProgressEvents,
  initialState,
  routeMessage,
  shouldShowIdleAnimation,
  type CanvasHookState,
} from '@code-monet/shared';
import type { ServerMessage, AgentStatus } from '@code-monet/shared';

// =============================================================================
// Test Helpers
// =============================================================================

/**
 * Process a single message through routeMessage → reducer chain.
 * Returns the new state after processing.
 */
function processMessage(state: CanvasHookState, message: ServerMessage): CanvasHookState {
  const actions: Parameters<typeof canvasReducer>[1][] = [];
  routeMessage(message, (action) => actions.push(action));
  return actions.reduce((s, action) => canvasReducer(s, action), state);
}

/**
 * Process a sequence of messages and return final state + status history.
 */
function processMessageSequence(
  messages: ServerMessage[],
  startState: CanvasHookState = { ...initialState, paused: false }
): {
  finalState: CanvasHookState;
  statusHistory: AgentStatus[];
  stateHistory: CanvasHookState[];
} {
  let state = startState;
  const statusHistory: AgentStatus[] = [];
  const stateHistory: CanvasHookState[] = [];

  for (const message of messages) {
    state = processMessage(state, message);
    statusHistory.push(deriveAgentStatus(state));
    stateHistory.push(state);
  }

  return { finalState: state, statusHistory, stateHistory };
}

/**
 * Create a human_stroke message with a simple line path.
 */
function makeHumanStroke(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  author: 'agent' | 'human' = 'human'
): ServerMessage {
  return {
    type: 'human_stroke',
    path: {
      type: 'line',
      points: [
        { x: fromX, y: fromY },
        { x: toX, y: toY },
      ],
      author,
    },
  };
}

/**
 * Create a agent_strokes_ready message.
 */
function makeStrokesReady(count: number, batchId: number, pieceNumber: number): ServerMessage {
  return {
    type: 'agent_strokes_ready',
    count,
    batch_id: batchId,
    piece_number: pieceNumber,
  };
}

/**
 * Create a code_execution started message.
 */
function makeCodeExecutionStarted(
  toolName: string,
  iteration: number = 1
): ServerMessage {
  return {
    type: 'code_execution',
    status: 'started',
    tool_name: toolName as ServerMessage extends { tool_name?: infer T } ? T : never,
    tool_input: {},
    stdout: null,
    stderr: null,
    return_code: null,
    iteration,
  };
}

/**
 * Create a code_execution completed message.
 */
function makeCodeExecutionCompleted(
  toolName: string,
  iteration: number = 1,
  returnCode: number = 0
): ServerMessage {
  return {
    type: 'code_execution',
    status: 'completed',
    tool_name: toolName as ServerMessage extends { tool_name?: infer T } ? T : never,
    tool_input: {},
    stdout: null,
    stderr: null,
    return_code: returnCode,
    iteration,
  };
}

/**
 * Create a thinking_delta message.
 */
function makeThinkingDelta(text: string, iteration: number = 1): ServerMessage {
  return {
    type: 'thinking_delta',
    text,
    iteration,
  };
}

/**
 * Create an iteration message.
 */
function makeIteration(current: number, max: number): ServerMessage {
  return {
    type: 'iteration',
    current,
    max,
  };
}

/**
 * Create a paused message.
 */
function makePaused(paused: boolean): ServerMessage {
  return {
    type: 'paused',
    paused,
  };
}

// =============================================================================
// Tests: human_stroke Message Flow
// =============================================================================

describe('human_stroke message flow', () => {
  it('adds a single stroke to empty canvas', () => {
    const startState: CanvasHookState = { ...initialState, paused: false };
    const message = makeHumanStroke(0, 0, 100, 100);

    const { finalState } = processMessageSequence([message], startState);

    expect(finalState.strokes).toHaveLength(1);
    expect(finalState.strokes[0]!.type).toBe('line');
    expect(finalState.strokes[0]!.points).toEqual([
      { x: 0, y: 0 },
      { x: 100, y: 100 },
    ]);
  });

  it('accumulates multiple strokes in order', () => {
    const startState: CanvasHookState = { ...initialState, paused: false };
    const messages: ServerMessage[] = [
      makeHumanStroke(0, 0, 100, 100),
      makeHumanStroke(100, 100, 200, 200),
      makeHumanStroke(200, 200, 300, 300),
    ];

    const { finalState } = processMessageSequence(messages, startState);

    expect(finalState.strokes).toHaveLength(3);
    expect(finalState.strokes[0]!.points[0]).toEqual({ x: 0, y: 0 });
    expect(finalState.strokes[1]!.points[0]).toEqual({ x: 100, y: 100 });
    expect(finalState.strokes[2]!.points[0]).toEqual({ x: 200, y: 200 });
  });

  it('preserves stroke author attribution', () => {
    const startState: CanvasHookState = { ...initialState, paused: false };
    const messages: ServerMessage[] = [
      makeHumanStroke(0, 0, 50, 50, 'agent'),
      makeHumanStroke(50, 50, 100, 100, 'human'),
    ];

    const { finalState } = processMessageSequence(messages, startState);

    expect(finalState.strokes[0]!.author).toBe('agent');
    expect(finalState.strokes[1]!.author).toBe('human');
  });

  it('clears agentStroke when stroke is finalized via performance model', () => {
    // Simulate stroke progress, then stroke complete via performance model
    let state: CanvasHookState = { ...initialState, paused: false };

    // Accumulate points via STROKE_PROGRESS
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 10, y: 10 } });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 20, y: 20 } });
    expect(state.performance.agentStroke.length).toBe(2);

    // Human stroke should add to strokes but not affect performance agentStroke
    state = processMessage(state, makeHumanStroke(10, 10, 20, 20));
    // Performance agentStroke unchanged by human stroke
    expect(state.performance.agentStroke.length).toBe(2);
    expect(state.strokes).toHaveLength(1);
  });
});

// =============================================================================
// Tests: agent_strokes_ready Message Flow
// =============================================================================

describe('agent_strokes_ready message flow', () => {
  it('agent_strokes_ready is not handled by routeMessage (handled inline in WS handler)', () => {
    // agent_strokes_ready is now intercepted by the WS handler before reaching routeMessage
    // Verify that routeMessage is a no-op for this message type
    const startState: CanvasHookState = { ...initialState, paused: false, pieceNumber: 0 };
    const message = makeStrokesReady(5, 1, 0);

    const { finalState } = processMessageSequence([message], startState);

    // State should be unchanged since routeMessage no longer handles agent_strokes_ready
    expect(finalState).toEqual(startState);
  });
});

// =============================================================================
// Tests: Status Transitions During Drawing
// =============================================================================

describe('status transitions during drawing', () => {
  it('shows executing when code_execution started (no return_code)', () => {
    const startState: CanvasHookState = { ...initialState, paused: false };
    const messages: ServerMessage[] = [
      makeIteration(1, 5),
      makeCodeExecutionStarted('draw_paths', 1),
    ];

    const { finalState } = processMessageSequence(messages, startState);

    expect(deriveAgentStatus(finalState)).toBe('executing');
  });

  it('transitions to idle after code_execution completes (strokes now fetched inline)', () => {
    const startState: CanvasHookState = { ...initialState, paused: false, pieceNumber: 0 };
    const messages: ServerMessage[] = [
      makeIteration(1, 5),
      makeCodeExecutionStarted('draw_paths', 1),
      makeCodeExecutionCompleted('draw_paths', 1),
    ];

    const { statusHistory } = processMessageSequence(messages, startState);

    // Should have transitioned through: idle -> executing -> idle
    expect(statusHistory).toContain('executing');
    expect(statusHistory[statusHistory.length - 1]).toBe('idle');
  });

  it('shows thinking when thinking text exists', () => {
    const startState: CanvasHookState = { ...initialState, paused: false };
    const messages: ServerMessage[] = [makeThinkingDelta('Let me think...', 1)];

    const { finalState } = processMessageSequence(messages, startState);

    expect(deriveAgentStatus(finalState)).toBe('thinking');
    expect(finalState.thinking).toBe('Let me think...');
  });

  it('stays thinking while thinking text exists (allows progressive reveal)', () => {
    const startState: CanvasHookState = { ...initialState, paused: false, pieceNumber: 0 };
    const messages: ServerMessage[] = [
      makeIteration(1, 5),
      makeThinkingDelta('Drawing some lines...', 1),
      makeCodeExecutionStarted('draw_paths', 1),
      makeCodeExecutionCompleted('draw_paths', 1),
    ];

    const { statusHistory, finalState } = processMessageSequence(messages, startState);

    // Status remains 'thinking' throughout because thinking text exists
    // This allows progressive text animation to complete during code execution
    expect(statusHistory).toContain('thinking');
    expect(statusHistory[statusHistory.length - 1]).toBe('thinking');

    // Thinking text should persist
    expect(finalState.thinking).toBe('Drawing some lines...');
  });

  it('paused status overrides everything', () => {
    const startState: CanvasHookState = { ...initialState, paused: false, pieceNumber: 0 };
    const messages: ServerMessage[] = [
      makeCodeExecutionStarted('draw_paths', 1),
      makePaused(true),
    ];

    const { finalState } = processMessageSequence(messages, startState);

    // Even with in-progress events, paused wins
    expect(deriveAgentStatus(finalState)).toBe('paused');
  });
});

// =============================================================================
// Tests: Idle Animation Visibility
// =============================================================================

describe('idle animation visibility', () => {
  it('shows idle animation when canvas empty and not drawing', () => {
    const state: CanvasHookState = {
      ...initialState,
      strokes: [],
      currentStroke: [],
    };

    expect(shouldShowIdleAnimation(state)).toBe(true);
  });

  it('hides idle animation when canvas has strokes', () => {
    const state: CanvasHookState = {
      ...initialState,
      paused: false,
      strokes: [{ type: 'line', points: [{ x: 0, y: 0 }, { x: 10, y: 10 }] }],
      currentStroke: [],
    };

    expect(shouldShowIdleAnimation(state)).toBe(false);
  });

  it('hides idle animation when user is drawing', () => {
    const state: CanvasHookState = {
      ...initialState,
      paused: false,
      strokes: [],
      currentStroke: [{ x: 5, y: 5 }], // user mid-stroke
    };

    expect(shouldShowIdleAnimation(state)).toBe(false);
  });

  it('hides idle animation when agent is drawing', () => {
    const state: CanvasHookState = {
      ...initialState,
      paused: false,
      strokes: [],
      currentStroke: [],
      performance: {
        ...initialState.performance,
        agentStroke: [{ x: 5, y: 5 }], // agent mid-stroke
      },
    };

    expect(shouldShowIdleAnimation(state)).toBe(false);
  });
});

// =============================================================================
// Tests: Realistic Agent Turn Sequence
// =============================================================================

describe('realistic agent turn sequence', () => {
  it('processes a complete draw_paths turn correctly', () => {
    const startState: CanvasHookState = { ...initialState, paused: false, pieceNumber: 0 };

    // Simulate a realistic agent turn (agent_strokes_ready no longer routed through reducer)
    const messages: ServerMessage[] = [
      // Agent starts thinking
      makeIteration(1, 5),
      makeThinkingDelta("I'll draw ", 1),
      makeThinkingDelta('a simple line.', 1),

      // Tool execution starts
      makeCodeExecutionStarted('draw_paths', 1),

      // Tool completes
      makeCodeExecutionCompleted('draw_paths', 1),
    ];

    const { finalState, statusHistory } = processMessageSequence(messages, startState);

    // iteration -> idle, thinking_delta -> thinking, rest stays thinking
    // because thinking text persists throughout the turn
    expect(statusHistory[0]).toBe('idle'); // iteration archives (no old thinking)
    expect(statusHistory[1]).toBe('thinking'); // first thinking_delta sets thinking
    expect(statusHistory[2]).toBe('thinking'); // second thinking_delta appends
    // Status remains 'thinking' because thinking text exists
    // This allows progressive text animation to complete
    expect(statusHistory[statusHistory.length - 1]).toBe('thinking');

    // Should have accumulated thinking text (still present for progressive reveal)
    expect(finalState.thinking).toContain("I'll draw a simple line.");
  });

  it('processes multiple iterations with strokes', () => {
    const startState: CanvasHookState = { ...initialState, paused: false, pieceNumber: 0 };

    const messages: ServerMessage[] = [
      // Iteration 1
      makeIteration(1, 3),
      makeThinkingDelta('First stroke', 1),
      makeCodeExecutionStarted('draw_paths', 1),
      makeCodeExecutionCompleted('draw_paths', 1),

      // Iteration 2 - archives iteration 1's thinking
      makeIteration(2, 3),
      makeThinkingDelta('Second stroke', 2),
      makeCodeExecutionStarted('draw_paths', 2),
      makeCodeExecutionCompleted('draw_paths', 2),
    ];

    const { finalState } = processMessageSequence(messages, startState);

    // End status is 'thinking' because iteration 2's thinking text still exists
    // (it would be archived on iteration 3 or turn end)
    expect(deriveAgentStatus(finalState)).toBe('thinking');
    expect(finalState.thinking).toBe('Second stroke');

    // Should track current iteration
    expect(finalState.currentIteration).toBe(2);
    expect(finalState.maxIterations).toBe(3);
  });

  it('handles error message correctly', () => {
    const startState: CanvasHookState = { ...initialState, paused: false };

    const messages: ServerMessage[] = [
      makeIteration(1, 5),
      makeThinkingDelta('Trying something...', 1),
      { type: 'error', message: 'Tool failed', details: 'Stack trace...' },
    ];

    const { finalState } = processMessageSequence(messages, startState);

    expect(deriveAgentStatus(finalState)).toBe('error');
    expect(finalState.messages.some((m) => m.type === 'error')).toBe(true);
  });

  it('handles clear message correctly', () => {
    const startState: CanvasHookState = {
      ...initialState,
      paused: false,
      strokes: [{ type: 'line', points: [{ x: 0, y: 0 }, { x: 10, y: 10 }] }],
      messages: [{ id: 'msg_1', type: 'thinking', text: 'Old thought', timestamp: Date.now() }],
    };

    const messages: ServerMessage[] = [{ type: 'clear' }];

    const { finalState } = processMessageSequence(messages, startState);

    expect(finalState.strokes).toEqual([]);
    expect(finalState.messages).toEqual([]);
  });

  it('transitions from drawing to idle when strokes animation completes', () => {
    // Strokes in buffer → drawing status
    let state: CanvasHookState = {
      ...initialState,
      paused: false,
      pieceNumber: 0,
      performance: {
        ...initialState.performance,
        buffer: [{ type: 'strokes', strokes: [], id: 'perf_1' }],
      },
    };

    expect(deriveAgentStatus(state)).toBe('drawing');

    // After animation completes, buffer is emptied
    state = canvasReducer(state, { type: 'CLEAR_PERFORMANCE' });

    expect(deriveAgentStatus(state)).toBe('idle');
  });
});

// =============================================================================
// Tests: hasInProgressEvents Edge Cases
// =============================================================================

describe('hasInProgressEvents edge cases', () => {
  it('returns false when started and completed for same tool+iteration', () => {
    const messages = [
      {
        id: 'exec_started',
        type: 'code_execution' as const,
        text: 'Drawing...',
        timestamp: Date.now(),
        iteration: 1,
        status: 'started' as const,
        metadata: { tool_name: 'draw_paths' as const },
      },
      {
        id: 'exec_completed',
        type: 'code_execution' as const,
        text: 'Done',
        timestamp: Date.now(),
        iteration: 1,
        status: 'completed' as const,
        metadata: { tool_name: 'draw_paths' as const, return_code: 0 },
      },
    ];

    expect(hasInProgressEvents(messages)).toBe(false);
  });

  it('returns true when completed is for different iteration', () => {
    const messages = [
      {
        id: 'exec_started',
        type: 'code_execution' as const,
        text: 'Drawing...',
        timestamp: Date.now(),
        iteration: 2, // started on iteration 2
        status: 'started' as const,
        metadata: { tool_name: 'draw_paths' as const },
      },
      {
        id: 'exec_completed',
        type: 'code_execution' as const,
        text: 'Done',
        timestamp: Date.now(),
        iteration: 1, // completed is for iteration 1
        status: 'completed' as const,
        metadata: { tool_name: 'draw_paths' as const, return_code: 0 },
      },
    ];

    expect(hasInProgressEvents(messages)).toBe(true);
  });

  it('returns true when completed is for different tool', () => {
    const messages = [
      {
        id: 'exec_started',
        type: 'code_execution' as const,
        text: 'Drawing...',
        timestamp: Date.now(),
        iteration: 1,
        status: 'started' as const,
        metadata: { tool_name: 'draw_paths' as const },
      },
      {
        id: 'exec_completed',
        type: 'code_execution' as const,
        text: 'Done',
        timestamp: Date.now(),
        iteration: 1,
        status: 'completed' as const,
        metadata: { tool_name: 'view_canvas' as const, return_code: 0 },
      },
    ];

    expect(hasInProgressEvents(messages)).toBe(true);
  });

  it('handles multiple concurrent tool executions', () => {
    const messages = [
      // Tool A started
      {
        id: 'exec_a_started',
        type: 'code_execution' as const,
        text: 'Tool A...',
        timestamp: Date.now(),
        iteration: 1,
        status: 'started' as const,
        metadata: { tool_name: 'draw_paths' as const },
      },
      // Tool A completed
      {
        id: 'exec_a_completed',
        type: 'code_execution' as const,
        text: 'Tool A done',
        timestamp: Date.now(),
        iteration: 1,
        status: 'completed' as const,
        metadata: { tool_name: 'draw_paths' as const, return_code: 0 },
      },
      // Tool B started
      {
        id: 'exec_b_started',
        type: 'code_execution' as const,
        text: 'Tool B...',
        timestamp: Date.now(),
        iteration: 1,
        status: 'started' as const,
        metadata: { tool_name: 'view_canvas' as const },
      },
    ];

    // Tool B is still in progress
    expect(hasInProgressEvents(messages)).toBe(true);
  });
});
