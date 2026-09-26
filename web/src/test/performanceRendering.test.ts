/**
 * Performance Rendering Integration Test
 *
 * Reproduces the bug: thinking_delta messages arrive via WebSocket,
 * but nothing renders (no thoughts above canvas, no strokes animate).
 *
 * This test verifies the full flow:
 * 1. WebSocket message -> routeMessage -> ENQUEUE_WORDS dispatch
 * 2. ENQUEUE_WORDS -> performance.buffer populated
 * 3. usePerformer -> ADVANCE_STAGE, REVEAL_WORD dispatched
 * 4. State -> revealedText populated for LiveStatus to render
 *
 * Run: npm run test -w web -- performanceRendering
 */

import { describe, it, expect } from 'vitest';
import {
  canvasReducer,
  initialState,
  routeMessage,
  type CanvasAction,
  type CanvasHookState,
  type ServerMessage,
} from '@code-monet/shared';

// ============================================================================
// Test Helpers
// ============================================================================

/**
 * Simulate receiving a WebSocket message and dispatching to reducer.
 */
function receiveMessage(state: CanvasHookState, message: ServerMessage): CanvasHookState {
  let newState = state;
  routeMessage(message, (action: CanvasAction) => {
    newState = canvasReducer(newState, action);
  });
  return newState;
}

/**
 * Simulate multiple thinking_delta messages arriving.
 */
function receiveThinkingDeltas(state: CanvasHookState, texts: string[]): CanvasHookState {
  let newState = state;
  for (const text of texts) {
    newState = receiveMessage(newState, {
      type: 'thinking_delta',
      text,
      iteration: 1,
    });
  }
  return newState;
}

// ============================================================================
// Bug Reproduction Tests
// ============================================================================

describe('Performance Rendering - Bug Reproduction', () => {
  it('ENQUEUE_WORDS populates performance.buffer when thinking_delta received', () => {
    let state = initialState;

    // Receive thinking_delta message
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Hello world',
      iteration: 1,
    });

    // Buffer should have words queued
    expect(state.performance.buffer.length).toBeGreaterThan(0);
    expect(state.performance.buffer[0]?.type).toBe('words');
  });

  it('multiple thinking_deltas accumulate in buffer', () => {
    let state = initialState;

    state = receiveThinkingDeltas(state, ['Hello ', 'world ', 'test']);

    // Each delta creates a separate buffer entry (words batch)
    // The exact count depends on implementation - at least 1
    expect(state.performance.buffer.length).toBeGreaterThanOrEqual(1);

    // All text should be captured across buffer entries
    const allText = state.performance.buffer
      .filter((item): item is { type: 'words'; text: string; id: string } => item.type === 'words')
      .map((item) => item.text)
      .join('');
    expect(allText).toContain('Hello');
    expect(allText).toContain('world');
    expect(allText).toContain('test');
  });

  it('ADVANCE_STAGE moves words from buffer to onStage', () => {
    let state = initialState;

    // Queue some words
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Hello world',
      iteration: 1,
    });

    expect(state.performance.buffer.length).toBe(1);
    expect(state.performance.onStage).toBeNull();

    // Advance stage (simulating what usePerformer does)
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Words should now be on stage
    expect(state.performance.onStage).not.toBeNull();
    expect(state.performance.onStage?.type).toBe('words');
    expect(state.performance.buffer.length).toBe(0);
  });

  it('REVEAL_WORD increments wordIndex and builds revealedText', () => {
    let state = initialState;

    // Queue words and advance to stage
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Hello world test',
      iteration: 1,
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.revealedText).toBe('');
    expect(state.performance.wordIndex).toBe(0);

    // Reveal first word
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    expect(state.performance.wordIndex).toBe(1);
    expect(state.performance.revealedText).toContain('Hello');

    // Reveal second word
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    expect(state.performance.wordIndex).toBe(2);
    expect(state.performance.revealedText).toContain('world');

    // Reveal third word
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    expect(state.performance.wordIndex).toBe(3);
    expect(state.performance.revealedText).toContain('test');
  });

  it('full flow: thinking_delta -> buffer -> stage -> revealedText', () => {
    let state = initialState;

    // 1. Receive thinking_delta (simulates WebSocket message)
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'A blank canvas',
      iteration: 1,
    });

    // 2. Buffer should be populated
    expect(state.performance.buffer.length).toBe(1);

    // 3. Advance to stage (usePerformer does this)
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    expect(state.performance.onStage?.type).toBe('words');

    // 4. Reveal words one by one (usePerformer animation loop)
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "A"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "blank"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "canvas"

    // 5. revealedText should contain all words
    expect(state.performance.revealedText).toBe('A blank canvas');
  });

  it('STAGE_COMPLETE fires when all words revealed', () => {
    let state = initialState;

    // Setup: queue and stage words
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Hi there',
      iteration: 1,
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Reveal all words
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "Hi"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "there"

    // Should be at end of words
    const onStage = state.performance.onStage;
    expect(onStage?.type).toBe('words');
    if (onStage?.type === 'words') {
      const wordCount = onStage.text.split(/\s+/).filter((w) => w.length > 0).length;
      expect(state.performance.wordIndex).toBe(wordCount);
    }

    // STAGE_COMPLETE should clear onStage
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });
    expect(state.performance.onStage).toBeNull();
  });
});

// ============================================================================
// Stroke Animation Tests
// ============================================================================

describe('Performance Rendering - Strokes', () => {
  it('ENQUEUE_STROKES populates buffer with strokes', () => {
    let state = initialState;

    const strokes = [
      {
        batch_id: 1,
        path: { type: 'polyline' as const, points: [{ x: 0, y: 0 }], author: 'agent' as const },
        points: [{ x: 0, y: 0 }],
      },
    ];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });

    expect(state.performance.buffer.length).toBe(1);
    expect(state.performance.buffer[0]?.type).toBe('strokes');
  });

  it('ADVANCE_STAGE moves strokes to onStage', () => {
    let state = initialState;

    const strokes = [
      {
        batch_id: 1,
        path: {
          type: 'polyline' as const,
          points: [
            { x: 0, y: 0 },
            { x: 10, y: 10 },
          ],
          author: 'agent' as const,
        },
        points: [
          { x: 0, y: 0 },
          { x: 10, y: 10 },
        ],
      },
    ];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.onStage?.type).toBe('strokes');
  });

  it('STROKE_PROGRESS builds agentStroke point by point', () => {
    let state = initialState;

    const strokes = [
      {
        batch_id: 1,
        path: {
          type: 'polyline' as const,
          points: [
            { x: 0, y: 0 },
            { x: 10, y: 10 },
            { x: 20, y: 20 },
          ],
          author: 'agent' as const,
        },
        points: [
          { x: 0, y: 0 },
          { x: 10, y: 10 },
          { x: 20, y: 20 },
        ],
      },
    ];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.agentStroke).toEqual([]);

    // Progress through points
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 0, y: 0 } });
    expect(state.performance.agentStroke).toEqual([{ x: 0, y: 0 }]);

    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 10, y: 10 } });
    expect(state.performance.agentStroke).toEqual([
      { x: 0, y: 0 },
      { x: 10, y: 10 },
    ]);

    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 20, y: 20 } });
    expect(state.performance.agentStroke).toEqual([
      { x: 0, y: 0 },
      { x: 10, y: 10 },
      { x: 20, y: 20 },
    ]);
  });

  it('STROKE_COMPLETE commits agentStroke to strokes array', () => {
    let state = initialState;

    const strokes = [
      {
        batch_id: 1,
        path: {
          type: 'polyline' as const,
          points: [
            { x: 0, y: 0 },
            { x: 10, y: 10 },
          ],
          author: 'agent' as const,
        },
        points: [
          { x: 0, y: 0 },
          { x: 10, y: 10 },
        ],
      },
    ];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Animate points
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 0, y: 0 } });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 10, y: 10 } });

    const strokeCountBefore = state.strokes.length;

    // Complete stroke
    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });

    // Stroke should be added to strokes array
    expect(state.strokes.length).toBe(strokeCountBefore + 1);
    // agentStroke should be cleared
    expect(state.performance.agentStroke).toEqual([]);
  });
});

// ============================================================================
// Bug Investigation: Why usePerformer doesn't animate
// ============================================================================

describe('usePerformer Prerequisites', () => {
  it('initialState has paused=true by design', () => {
    // usePerformer early-returns if paused
    // App starts paused - user must click "Start" or "Continue" to unpause
    const state = initialState;

    // Default is PAUSED - this is intentional
    expect(state.paused).toBe(true);

    // This means usePerformer won't run until:
    // 1. User submits prompt (calls setPaused(false))
    // 2. Server confirms resume (sends paused=false message)
  });

  it('requires paused=false to run animation', () => {
    let state = initialState;

    // When paused, animation doesn't run
    state = canvasReducer(state, { type: 'SET_PAUSED', paused: true });
    expect(state.paused).toBe(true);

    // Words can still be enqueued while paused
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Hello',
      iteration: 1,
    });
    expect(state.performance.buffer.length).toBe(1);

    // But usePerformer won't process them until unpaused
  });

  it('buffer persists when animation conditions not met', () => {
    let state = initialState;

    // Enqueue words
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Waiting to animate',
      iteration: 1,
    });

    // Buffer has items
    expect(state.performance.buffer.length).toBe(1);

    // onStage is null (ADVANCE_STAGE not called yet)
    expect(state.performance.onStage).toBeNull();

    // revealedText is empty (no REVEAL_WORD called)
    expect(state.performance.revealedText).toBe('');

    // This is the bug state: buffer has content but nothing renders
    // because usePerformer isn't calling ADVANCE_STAGE and REVEAL_WORD
  });
});

// ============================================================================
// Full Session Flow Test
// ============================================================================

describe('Full Session Flow', () => {
  it('simulates complete session: init -> new_canvas -> paused=false -> thinking_delta', () => {
    let state = initialState;

    // 1. WebSocket init (server sends current state with paused=true)
    state = receiveMessage(state, {
      type: 'init',
      strokes: [],
      gallery: [],
      status: 'paused',
      paused: true,
      piece_number: 1,
      monologue: '',
      drawing_style: 'plotter',
      style_config: undefined,
    });
    expect(state.paused).toBe(true);

    // 2. Server confirms new_canvas
    state = receiveMessage(state, {
      type: 'new_canvas',
      saved_id: 'piece_000001',
    });
    // new_canvas clears the performance buffer
    expect(state.performance.buffer.length).toBe(0);

    // 3. Server sends paused=false after resume
    state = receiveMessage(state, {
      type: 'paused',
      paused: false,
    });
    expect(state.paused).toBe(false);

    // 4. Agent starts producing thinking_delta
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Let me draw a red circle',
      iteration: 1,
    });

    // Buffer should have words
    expect(state.performance.buffer.length).toBe(1);
    expect(state.performance.buffer[0]?.type).toBe('words');

    // Thinking text should accumulate (for archive)
    expect(state.thinking).toBe('Let me draw a red circle');

    // 5. Simulate usePerformer animation (manually since we're not testing the hook here)
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    expect(state.performance.onStage?.type).toBe('words');

    // Reveal words
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "Let"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "me"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "draw"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "a"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "red"
    state = canvasReducer(state, { type: 'REVEAL_WORD' }); // "circle"

    // revealedText should contain the full text
    expect(state.performance.revealedText).toBe('Let me draw a red circle');
  });

  it('handles race: thinking_delta arrives while still paused (queued for later)', () => {
    let state = initialState;

    // Start with init (paused=true)
    state = receiveMessage(state, {
      type: 'init',
      strokes: [],
      gallery: [],
      status: 'paused',
      paused: true,
      piece_number: 1,
      monologue: '',
      drawing_style: 'plotter',
      style_config: undefined,
    });
    expect(state.paused).toBe(true);

    // Thinking arrives even though paused (rare but possible)
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Starting work',
      iteration: 1,
    });

    // Buffer IS populated regardless of paused state
    // (paused only affects usePerformer animation, not message routing)
    expect(state.performance.buffer.length).toBe(1);

    // But paused is still true, so usePerformer won't animate yet
    expect(state.paused).toBe(true);

    // When paused goes false, usePerformer will start processing the buffer
    state = receiveMessage(state, {
      type: 'paused',
      paused: false,
    });
    expect(state.paused).toBe(false);
    expect(state.performance.buffer.length).toBe(1); // Buffer still there, waiting for animation
  });

  it('paused message from server overrides local state', () => {
    let state = initialState;

    // Local state starts paused=true
    expect(state.paused).toBe(true);

    // Direct reducer action sets paused=false (simulates canvas.setPaused(false))
    state = canvasReducer(state, { type: 'SET_PAUSED', paused: false });
    expect(state.paused).toBe(false);

    // Server sends paused=true (e.g., agent finished or error)
    state = receiveMessage(state, {
      type: 'paused',
      paused: true,
    });
    // Server message overrides local state
    expect(state.paused).toBe(true);
  });
});

// ============================================================================
// Event Replaces Thinking Text
// ============================================================================

describe('Event Replaces Thinking Text', () => {
  it('ADVANCE_STAGE clears revealedText when event advances to stage', () => {
    let state = initialState;

    // Build up revealed text
    state = receiveMessage(state, { type: 'thinking_delta', text: 'Hello world', iteration: 1 });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    expect(state.performance.revealedText).toBe('Hello world');

    // Complete words stage
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });
    expect(state.performance.onStage).toBeNull();

    // Enqueue event
    state = canvasReducer(state, {
      type: 'ENQUEUE_EVENT',
      message: {
        id: 'test-1',
        type: 'code_execution',
        text: 'Drawing 5 paths...',
        timestamp: Date.now(),
        status: 'started',
        metadata: { tool_name: 'draw_paths' },
      },
    });

    // Advance event to stage - should clear revealedText
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    expect(state.performance.revealedText).toBe('');
    expect(state.performance.onStage?.type).toBe('event');
  });

  it('revealedText stays empty after event completes', () => {
    let state = initialState;

    // Build up revealed text, then advance event
    state = receiveMessage(state, { type: 'thinking_delta', text: 'Thinking...', iteration: 1 });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    // Enqueue and advance event
    state = canvasReducer(state, {
      type: 'ENQUEUE_EVENT',
      message: {
        id: 'test-1',
        type: 'code_execution',
        text: 'Executing...',
        timestamp: Date.now(),
        status: 'started',
      },
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    expect(state.performance.revealedText).toBe('');

    // Complete the event
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });
    expect(state.performance.onStage).toBeNull();

    // revealedText should still be empty - old thinking doesn't come back
    expect(state.performance.revealedText).toBe('');
  });

  it('new words after event start fresh', () => {
    let state = initialState;

    // Old thinking
    state = receiveMessage(state, { type: 'thinking_delta', text: 'Old thinking', iteration: 1 });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    // Event clears thinking
    state = canvasReducer(state, {
      type: 'ENQUEUE_EVENT',
      message: { id: 'e1', type: 'code_execution', text: 'Running...', timestamp: Date.now() },
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    // New thinking arrives
    state = receiveMessage(state, { type: 'thinking_delta', text: 'New thinking', iteration: 2 });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });

    // Should show new thinking, not old
    expect(state.performance.revealedText).toBe('New thinking');
    expect(state.performance.revealedText).not.toContain('Old');
  });

  it('strokes do NOT clear revealedText (only events do)', () => {
    let state = initialState;

    // Build up revealed text
    state = receiveMessage(state, { type: 'thinking_delta', text: 'Keep showing', iteration: 1 });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    expect(state.performance.revealedText).toBe('Keep showing');
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    // Enqueue and advance strokes
    const strokes = [
      {
        batch_id: 1,
        path: { type: 'polyline' as const, points: [{ x: 0, y: 0 }], author: 'agent' as const },
        points: [{ x: 0, y: 0 }],
      },
    ];
    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // revealedText should STILL show - strokes don't clear it
    expect(state.performance.revealedText).toBe('Keep showing');
    expect(state.performance.onStage?.type).toBe('strokes');
  });
});

// ============================================================================
// Integration: What LiveStatus Needs
// ============================================================================

describe('LiveStatus Data Requirements', () => {
  it('revealedText is available for display after word reveal', () => {
    let state = initialState;

    // Simulate full message flow
    state = receiveMessage(state, {
      type: 'thinking_delta',
      text: 'Processing your request',
      iteration: 1,
    });

    // Advance and reveal (what usePerformer does)
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });

    // This is what LiveStatus reads to display thoughts
    expect(state.performance.revealedText.length).toBeGreaterThan(0);
    expect(state.performance.revealedText).toBe('Processing your request');
  });

  it('agentStroke is available for Canvas to render during animation', () => {
    let state = initialState;

    const strokes = [
      {
        batch_id: 1,
        path: {
          type: 'polyline' as const,
          points: [
            { x: 100, y: 100 },
            { x: 200, y: 200 },
          ],
          author: 'agent' as const,
        },
        points: [
          { x: 100, y: 100 },
          { x: 200, y: 200 },
        ],
      },
    ];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 100, y: 100 } });

    // This is what Canvas reads to render the in-progress stroke
    expect(state.performance.agentStroke.length).toBeGreaterThan(0);
    expect(state.performance.agentStroke[0]).toEqual({ x: 100, y: 100 });
  });
});
