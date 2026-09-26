/**
 * Stroke Animation Tests - Performance Model
 *
 * Tests the deterministic stroke animation flow:
 * 1. ENQUEUE_STROKES - add strokes to buffer
 * 2. ADVANCE_STAGE - move strokes to stage
 * 3. STROKE_PROGRESS - animate points (pen moves)
 * 4. STROKE_COMPLETE - finish stroke, add to main array
 * 5. STAGE_COMPLETE - clear stage when all strokes done
 *
 * Run: npm run test -w web -- strokeAnimation
 */

import { describe, it, expect } from 'vitest';
import { canvasReducer, initialState, type CanvasHookState } from '@code-monet/shared';
import type { PendingStroke, Point, StrokeStyle } from '@code-monet/shared';

/**
 * Create a test stroke with given points.
 */
function makeStroke(points: Point[], author: 'agent' | 'human' = 'agent'): PendingStroke {
  return {
    batch_id: 0,
    path: {
      type: 'polyline',
      points,
      author,
    },
    points, // Pre-interpolated points (same as path.points for test)
  };
}

describe('Stroke Animation - ENQUEUE_STROKES', () => {
  it('adds strokes to buffer', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const strokes = [
      makeStroke([
        { x: 0, y: 0 },
        { x: 100, y: 100 },
      ]),
    ];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });

    expect(state.performance.buffer).toHaveLength(1);
    expect(state.performance.buffer[0]?.type).toBe('strokes');
    if (state.performance.buffer[0]?.type === 'strokes') {
      expect(state.performance.buffer[0].strokes).toEqual(strokes);
    }
  });

  it('accumulates multiple stroke batches in buffer', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const batch1 = [makeStroke([{ x: 0, y: 0 }])];
    const batch2 = [makeStroke([{ x: 10, y: 10 }])];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes: batch1 });
    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes: batch2 });

    expect(state.performance.buffer).toHaveLength(2);
  });

  it('assigns unique IDs to each buffer item', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 1, y: 1 }])],
    });

    const ids = state.performance.buffer.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length); // All unique
  });
});

describe('Stroke Animation - ADVANCE_STAGE', () => {
  it('moves first buffer item to stage', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const strokes = [makeStroke([{ x: 0, y: 0 }])];
    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.onStage?.type).toBe('strokes');
    expect(state.performance.buffer).toHaveLength(0);
  });

  it('does nothing if stage is occupied', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 1, y: 1 }])],
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Stage occupied
    expect(state.performance.onStage).not.toBeNull();
    expect(state.performance.buffer).toHaveLength(1);

    // Try to advance again - should be no-op
    const prevState = state;
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.onStage).toBe(prevState.performance.onStage);
    expect(state.performance.buffer).toHaveLength(1);
  });

  it('does nothing if buffer is empty', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.onStage).toBeNull();
  });

  it('resets stroke animation state when advancing to strokes', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.strokeIndex).toBe(0);
    expect(state.performance.strokeProgress).toBe(0);
  });
});

describe('Stroke Animation - STROKE_PROGRESS', () => {
  it('accumulates points in agentStroke', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 10, y: 10 } });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 20, y: 20 } });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 30, y: 30 } });

    expect(state.performance.agentStroke).toEqual([
      { x: 10, y: 10 },
      { x: 20, y: 20 },
      { x: 30, y: 30 },
    ]);
  });

  it('updates pen position', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 50, y: 75 } });

    expect(state.performance.penPosition).toEqual({ x: 50, y: 75 });
  });

  it('sets pen down', () => {
    let state: CanvasHookState = { ...initialState, paused: false };
    expect(state.performance.penDown).toBe(false);

    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 10, y: 10 } });

    expect(state.performance.penDown).toBe(true);
  });

  it('captures stroke style on first point', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const style: StrokeStyle = {
      color: '#FF0000',
      stroke_width: 5,
      opacity: 1,
      stroke_linecap: 'round',
      stroke_linejoin: 'round',
    };
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 10, y: 10 }, style });

    expect(state.performance.agentStrokeStyle).toEqual(style);
  });

  it('does not override style on subsequent points', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const style1: StrokeStyle = {
      color: '#FF0000',
      stroke_width: 5,
      opacity: 1,
      stroke_linecap: 'round',
      stroke_linejoin: 'round',
    };
    const style2: StrokeStyle = {
      color: '#00FF00',
      stroke_width: 10,
      opacity: 1,
      stroke_linecap: 'round',
      stroke_linejoin: 'round',
    };

    state = canvasReducer(state, {
      type: 'STROKE_PROGRESS',
      point: { x: 10, y: 10 },
      style: style1,
    });
    state = canvasReducer(state, {
      type: 'STROKE_PROGRESS',
      point: { x: 20, y: 20 },
      style: style2,
    });

    expect(state.performance.agentStrokeStyle).toEqual(style1);
  });
});

describe('Stroke Animation - STROKE_COMPLETE', () => {
  it('adds stroke to main strokes array', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // Enqueue and advance
    const stroke = makeStroke([
      { x: 0, y: 0 },
      { x: 100, y: 100 },
    ]);
    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes: [stroke] });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Simulate progress (not strictly needed but realistic)
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 0, y: 0 } });

    // Complete the stroke
    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });

    expect(state.strokes).toHaveLength(1);
    expect(state.strokes[0]).toEqual(stroke.path);
  });

  it('advances stroke index', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const strokes = [makeStroke([{ x: 0, y: 0 }]), makeStroke([{ x: 10, y: 10 }])];
    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.strokeIndex).toBe(0);

    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    expect(state.performance.strokeIndex).toBe(1);

    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    expect(state.performance.strokeIndex).toBe(2);
  });

  it('resets agentStroke and pen state', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 50, y: 50 } });

    expect(state.performance.agentStroke).toHaveLength(1);
    expect(state.performance.penDown).toBe(true);

    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });

    expect(state.performance.agentStroke).toHaveLength(0);
    expect(state.performance.penDown).toBe(false);
  });

  it('clears stroke style', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const style: StrokeStyle = {
      color: '#FF0000',
      stroke_width: 5,
      opacity: 1,
      stroke_linecap: 'round',
      stroke_linejoin: 'round',
    };
    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 0, y: 0 }, style });

    expect(state.performance.agentStrokeStyle).not.toBeNull();

    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });

    expect(state.performance.agentStrokeStyle).toBeNull();
  });

  it('does nothing if stage has no strokes', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // Stage is empty
    const prevState = state;
    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });

    expect(state).toBe(prevState);
  });
});

describe('Stroke Animation - STAGE_COMPLETE', () => {
  it('clears stage after all strokes complete', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.onStage).not.toBeNull();

    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    expect(state.performance.onStage).toBeNull();
  });

  it('adds completed item to history', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    const onStageId = state.performance.onStage?.id;

    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    expect(state.performance.history.some((item) => item.id === onStageId)).toBe(true);
  });
});

describe('Stroke Animation - Full Flow', () => {
  it('processes multiple strokes in sequence', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const strokes = [
      makeStroke([
        { x: 0, y: 0 },
        { x: 50, y: 50 },
      ]),
      makeStroke([
        { x: 100, y: 100 },
        { x: 150, y: 150 },
      ]),
    ];

    // Enqueue and advance to stage
    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Animate first stroke
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 0, y: 0 } });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 50, y: 50 } });
    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });

    expect(state.strokes).toHaveLength(1);
    expect(state.performance.strokeIndex).toBe(1);

    // Animate second stroke
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 100, y: 100 } });
    state = canvasReducer(state, { type: 'STROKE_PROGRESS', point: { x: 150, y: 150 } });
    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });

    expect(state.strokes).toHaveLength(2);
    expect(state.performance.strokeIndex).toBe(2);

    // Complete stage
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    expect(state.performance.onStage).toBeNull();
    expect(state.strokes).toHaveLength(2);
  });

  it('queues new strokes while animating', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // First batch
    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // New batch arrives while animating
    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 10, y: 10 }])],
    });

    expect(state.performance.onStage).not.toBeNull();
    expect(state.performance.buffer).toHaveLength(1);

    // Finish first batch
    state = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    expect(state.performance.onStage).toBeNull();
    expect(state.performance.buffer).toHaveLength(1);

    // Advance to second batch
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    expect(state.performance.onStage).not.toBeNull();
    expect(state.performance.buffer).toHaveLength(0);
  });

  it('preserves stroke order', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    const strokes = [
      makeStroke([{ x: 1, y: 1 }]),
      makeStroke([{ x: 2, y: 2 }]),
      makeStroke([{ x: 3, y: 3 }]),
    ];

    state = canvasReducer(state, { type: 'ENQUEUE_STROKES', strokes });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Complete all strokes
    for (let i = 0; i < 3; i++) {
      state = canvasReducer(state, { type: 'STROKE_COMPLETE' });
    }
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    expect(state.strokes).toHaveLength(3);
    expect(state.strokes[0]?.points[0]).toEqual({ x: 1, y: 1 });
    expect(state.strokes[1]?.points[0]).toEqual({ x: 2, y: 2 });
    expect(state.strokes[2]?.points[0]).toEqual({ x: 3, y: 3 });
  });
});

describe('Stroke Animation - Mixed Performance Items', () => {
  it('alternates between words and strokes in buffer', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // Queue words, strokes, words
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'Starting' });
    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'Done' });

    expect(state.performance.buffer).toHaveLength(3);
    expect(state.performance.buffer[0]?.type).toBe('words');
    expect(state.performance.buffer[1]?.type).toBe('strokes');
    expect(state.performance.buffer[2]?.type).toBe('words');
  });

  it('processes different item types in order', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // Queue words then strokes
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'Drawing' });
    state = canvasReducer(state, {
      type: 'ENQUEUE_STROKES',
      strokes: [makeStroke([{ x: 0, y: 0 }])],
    });

    // Advance to words
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    expect(state.performance.onStage?.type).toBe('words');

    // Complete words
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });

    // Advance to strokes
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });
    expect(state.performance.onStage?.type).toBe('strokes');
  });
});
