/**
 * Reducer replay tests - validate app state machine with recorded WebSocket messages.
 *
 * These tests replay fixtures recorded from real agent turns to ensure the
 * app reducer produces the correct final state. They are:
 * - Deterministic: Same fixture = same test results
 * - Fast: No API calls, pure state machine testing
 * - Connected: Validates real server output processed by real app code
 *
 * Run: npm test -- --testPathPattern=reducer.replay
 */

import {
  canvasReducer,
  deriveAgentStatus,
  hasInProgressEvents,
  initialState,
  routeMessage,
  type CanvasHookState,
} from '@code-monet/shared';
import type { ServerMessage, AgentStatus } from '@code-monet/shared';

// Import fixture - using relative path since symlinks may not work in all envs
import fixture from './fixtures/server/agent_turn_plotter.json';

interface FixtureMessage {
  type: string;
  data: ServerMessage;
  timestamp_ms: number;
}

interface Fixture {
  metadata: {
    model: string;
    style: string;
    recorded_at: string;
    description: string;
    message_count: number;
  };
  messages: FixtureMessage[];
}

/**
 * Process a single message through the routing/reducer chain.
 * Returns the new state after processing.
 */
function processMessage(state: CanvasHookState, message: ServerMessage): CanvasHookState {
  // Collect actions dispatched by routeMessage
  const actions: Parameters<typeof canvasReducer>[1][] = [];
  const dispatch = (action: Parameters<typeof canvasReducer>[1]) => {
    actions.push(action);
  };

  routeMessage(message, dispatch);

  // Apply all actions to produce new state
  return actions.reduce((s, action) => canvasReducer(s, action), state);
}

/**
 * Replay all messages through the reducer chain.
 * Returns the final state and intermediate statuses.
 */
function replayMessages(messages: FixtureMessage[]): {
  finalState: CanvasHookState;
  statuses: AgentStatus[];
  actions: string[];
} {
  let state: CanvasHookState = { ...initialState, paused: false };
  const statuses: AgentStatus[] = [];
  const actions: string[] = [];

  for (const msg of messages) {
    // Track actions for debugging
    const dispatch = (action: Parameters<typeof canvasReducer>[1]) => {
      actions.push(action.type);
      state = canvasReducer(state, action);
    };

    routeMessage(msg.data, dispatch);
    statuses.push(deriveAgentStatus(state));
  }

  return { finalState: state, statuses, actions };
}

describe('Reducer Replay - Plotter Style Turn', () => {
  const typedFixture = fixture as Fixture;

  describe('fixture validation', () => {
    it('has valid metadata', () => {
      expect(typedFixture.metadata).toBeDefined();
      expect(typedFixture.metadata.style).toBe('plotter');
      expect(typedFixture.metadata.message_count).toBeGreaterThan(0);
    });

    it('has messages array', () => {
      expect(typedFixture.messages).toBeDefined();
      expect(Array.isArray(typedFixture.messages)).toBe(true);
      expect(typedFixture.messages.length).toBe(typedFixture.metadata.message_count);
    });

    it('has monotonically increasing timestamps', () => {
      const timestamps = typedFixture.messages.map((m) => m.timestamp_ms);
      for (let i = 1; i < timestamps.length; i++) {
        expect(timestamps[i]).toBeGreaterThanOrEqual(timestamps[i - 1]!);
      }
    });
  });

  describe('complete turn replay', () => {
    it('processes all messages without errors', () => {
      const { finalState, actions } = replayMessages(typedFixture.messages);

      expect(actions.length).toBeGreaterThan(0);
      expect(finalState).toBeDefined();
    });

    it('produces expected final state', () => {
      const { finalState } = replayMessages(typedFixture.messages);

      // Should have messages from the turn
      expect(finalState.messages.length).toBeGreaterThan(0);

      // If fixture ends with piece_state, pieceNumber should be set
      const lastPieceState = typedFixture.messages.filter((m) => m.type === 'piece_state').pop();

      if (lastPieceState && lastPieceState.data.type === 'piece_state') {
        expect(finalState.pieceNumber).toBe(lastPieceState.data.number);
      }
    });

    it('ends in valid status after turn completes', () => {
      const { finalState, statuses } = replayMessages(typedFixture.messages);

      // Final status depends on fixture content:
      // - 'thinking' if ends with live message (thinking_delta without finalization)
      // - 'drawing' if strokes in performance buffer
      // - 'idle' if all events completed
      // - 'executing' if code_execution started but not completed
      const finalStatus = deriveAgentStatus(finalState);
      expect(['idle', 'drawing', 'thinking', 'executing']).toContain(finalStatus);

      // Should have gone through thinking or executing states during the turn
      expect(statuses.some((s) => s === 'thinking' || s === 'executing')).toBe(true);
    });
  });

  describe('status transitions', () => {
    it('shows iteration -> thinking transition', () => {
      const { statuses } = replayMessages(typedFixture.messages);

      // After iteration, we may see thinking if thinking_delta follows
      const hasThinking = statuses.includes('thinking');
      const hasExecuting = statuses.includes('executing');

      // Should have at least one of these states
      expect(hasThinking || hasExecuting).toBe(true);
    });

    it('has in-progress event when code_execution starts', () => {
      // Find code_execution started message
      const codeStartIndex = typedFixture.messages.findIndex(
        (m) =>
          m.type === 'code_execution' &&
          m.data.type === 'code_execution' &&
          m.data.status === 'started'
      );

      if (codeStartIndex === -1) {
        // No code execution in this fixture - skip
        return;
      }

      // Replay up to and including the started message
      const messagesToReplay = typedFixture.messages.slice(0, codeStartIndex + 1);
      const { finalState } = replayMessages(messagesToReplay);

      // Should have an in-progress event (code is executing)
      // Note: status may be 'thinking' if live message exists, or 'executing' if not
      // What matters is that hasInProgressEvents returns true
      expect(hasInProgressEvents(finalState.messages)).toBe(true);
    });

    it('transitions out of executing when code_execution completes', () => {
      // Find code_execution completed message
      const codeCompleteIndex = typedFixture.messages.findIndex(
        (m) =>
          m.type === 'code_execution' &&
          m.data.type === 'code_execution' &&
          m.data.status === 'completed'
      );

      if (codeCompleteIndex === -1) {
        return;
      }

      // Replay up to and including the completed message
      const messagesToReplay = typedFixture.messages.slice(0, codeCompleteIndex + 1);
      const { finalState } = replayMessages(messagesToReplay);

      const lastStatus = deriveAgentStatus(finalState);
      // Should no longer be executing
      expect(lastStatus).not.toBe('executing');
    });
  });

  describe('message accumulation', () => {
    it('accumulates thinking deltas', () => {
      const thinkingDeltas = typedFixture.messages.filter((m) => m.type === 'thinking_delta');

      if (thinkingDeltas.length === 0) {
        return;
      }

      const { finalState } = replayMessages(typedFixture.messages);

      // Should have accumulated thinking text
      expect(finalState.thinking.length).toBeGreaterThan(0);

      // Total text should be at least the sum of deltas
      // (may include finalized message too)
      const totalDeltaLength = thinkingDeltas.reduce((sum, m) => {
        const data = m.data as { text?: string };
        return sum + (data.text?.length || 0);
      }, 0);

      expect(finalState.thinking.length).toBeGreaterThanOrEqual(totalDeltaLength);
    });

    it('creates messages for code execution events', () => {
      const { finalState } = replayMessages(typedFixture.messages);

      // Count code_execution messages in fixture
      const codeExecCount = typedFixture.messages.filter((m) => m.type === 'code_execution').length;

      if (codeExecCount === 0) {
        return;
      }

      // Should have corresponding AgentMessages
      const codeExecMessages = finalState.messages.filter((m) => m.type === 'code_execution');
      expect(codeExecMessages.length).toBe(codeExecCount);
    });
  });

  describe('gallery updates', () => {
    it('updates gallery when gallery_update received', () => {
      const galleryUpdates = typedFixture.messages.filter((m) => m.type === 'gallery_update');

      if (galleryUpdates.length === 0) {
        return;
      }

      const { finalState } = replayMessages(typedFixture.messages);

      // Gallery should be populated
      expect(finalState.gallery.length).toBeGreaterThan(0);

      // Should match the last gallery_update
      const lastGalleryUpdate = galleryUpdates[galleryUpdates.length - 1]!;
      const lastData = lastGalleryUpdate.data as { canvases?: unknown[] };
      expect(finalState.gallery.length).toBe(lastData.canvases?.length ?? 0);
    });
  });

  describe('agent strokes ready handling', () => {
    it('agent_strokes_ready dispatches no actions (handled inline in WS handler)', () => {
      const strokesReadyMsg = typedFixture.messages.find(
        (m) => m.type === 'agent_strokes_ready'
      );

      if (!strokesReadyMsg) {
        return;
      }

      // Verify routeMessage dispatches no actions for agent_strokes_ready
      const actions: string[] = [];
      routeMessage(strokesReadyMsg.data, (action) => actions.push(action.type));
      expect(actions).toEqual([]);
    });
  });
});

describe('Reducer Replay - Error Handling', () => {
  it('handles error message correctly', () => {
    const errorMessage: ServerMessage = {
      type: 'error',
      message: 'Test error',
      details: 'Error details',
    };

    let state: CanvasHookState = { ...initialState, paused: false };
    state = processMessage(state, errorMessage);

    const status = deriveAgentStatus(state);
    expect(status).toBe('error');

    const errorMessages = state.messages.filter((m) => m.type === 'error');
    expect(errorMessages.length).toBe(1);
    expect(errorMessages[0]!.text).toBe('Test error');
  });
});
