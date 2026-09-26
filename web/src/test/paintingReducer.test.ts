/**
 * Program-painting reducer state and painting_version routing.
 */

import { describe, expect, it } from 'vitest';
import type {
  CanvasAction,
  CanvasHookState,
  PaintingVersionMessage,
  PaintingVersionRef,
} from '@code-monet/shared';
import {
  canvasReducer,
  deriveAgentStatus,
  initialState,
  routeMessage,
  shouldShowIdleAnimation,
} from '@code-monet/shared';

const ref = (piece: number, version: number): PaintingVersionRef => ({
  piece_number: piece,
  version,
  asset_base: `/painting-assets/u/p${piece}v${version}/`,
  image_width: 1600,
  image_height: 1200,
});

const reduce = (state: CanvasHookState, ...actions: CanvasAction[]): CanvasHookState =>
  actions.reduce(canvasReducer, state);

const atPiece = (n: number): CanvasHookState => ({
  ...initialState,
  pieceNumber: n,
  paused: false,
});

describe('painting reducer', () => {
  it('starts playing the first version over a blank base', () => {
    const s = reduce(atPiece(3), { type: 'PAINTING_VERSION', version: ref(3, 1) });
    expect(s.painting).toEqual({ base: null, playing: ref(3, 1) });
    expect(deriveAgentStatus(s)).toBe('drawing');
    expect(shouldShowIdleAnimation(s)).toBe(false);
  });

  it('promotes the playing version to base when playback finishes', () => {
    const s = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'PAINTING_PLAYBACK_DONE', assetBase: ref(3, 1).asset_base }
    );
    expect(s.painting).toEqual({ base: ref(3, 1), playing: null });
    expect(deriveAgentStatus(s)).toBe('idle');
  });

  it('ignores playback-done for a version that is not playing', () => {
    const s0 = reduce(atPiece(3), { type: 'PAINTING_VERSION', version: ref(3, 2) });
    const s1 = reduce(s0, { type: 'PAINTING_PLAYBACK_DONE', assetBase: ref(3, 1).asset_base });
    expect(s1).toBe(s0);
  });

  it('finishes the current version when another arrives mid-playback', () => {
    const s = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'PAINTING_VERSION', version: ref(3, 2) }
    );
    expect(s.painting).toEqual({ base: ref(3, 1), playing: ref(3, 2) });
  });

  it('ignores duplicate or older versions of the same piece', () => {
    const s0 = reduce(atPiece(3), { type: 'PAINTING_VERSION', version: ref(3, 2) });
    expect(reduce(s0, { type: 'PAINTING_VERSION', version: ref(3, 2) })).toBe(s0);
    expect(reduce(s0, { type: 'PAINTING_VERSION', version: ref(3, 1) })).toBe(s0);
  });

  it('ignores versions for an older piece', () => {
    const s0 = atPiece(5);
    expect(reduce(s0, { type: 'PAINTING_VERSION', version: ref(4, 1) })).toBe(s0);
  });

  it('ignores versions while viewing a gallery piece', () => {
    const s0 = { ...atPiece(3), viewingPiece: 1 };
    expect(reduce(s0, { type: 'PAINTING_VERSION', version: ref(3, 1) })).toBe(s0);
  });

  it('syncs the piece number and drops the old base for a newer piece', () => {
    const s = reduce(
      { ...atPiece(3), painting: { base: ref(3, 4), playing: null } },
      { type: 'PAINTING_VERSION', version: ref(4, 1) }
    );
    expect(s.pieceNumber).toBe(4);
    expect(s.painting).toEqual({ base: null, playing: ref(4, 1) });
  });

  it('resets on CLEAR', () => {
    const s = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'CLEAR' }
    );
    expect(s.painting).toEqual({ base: null, playing: null });
  });

  it('INIT shows the current version without animating', () => {
    const s = reduce(atPiece(0), {
      type: 'INIT',
      strokes: [],
      gallery: [],
      pieceNumber: 7,
      paused: true,
      painting: ref(7, 3),
    });
    expect(s.painting).toEqual({ base: ref(7, 3), playing: null });
    const none = reduce(s, {
      type: 'INIT',
      strokes: [],
      gallery: [],
      pieceNumber: 8,
      paused: true,
    });
    expect(none.painting).toEqual({ base: null, playing: null });
  });

  it('hides the painting while viewing a gallery piece and restores it after', () => {
    const viewing = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'LOAD_CANVAS', strokes: [], pieceNumber: 1 }
    );
    expect(viewing.painting).toEqual({ base: null, playing: null });
    const back = reduce(viewing, { type: 'CLEAR_VIEWING' });
    // In-flight playback is collapsed to its final on the way out
    expect(back.painting).toEqual({ base: ref(3, 1), playing: null });
  });
});

describe('painting_version routing', () => {
  const collect = (msg: Parameters<typeof routeMessage>[0]): CanvasAction[] => {
    const actions: CanvasAction[] = [];
    routeMessage(msg, (a) => actions.push(a));
    return actions;
  };

  it('dispatches PAINTING_VERSION with the stage list and op count', () => {
    const msg: PaintingVersionMessage = {
      type: 'painting_version',
      ...ref(12, 3),
      stages: ['ground', 'sky'],
      ops: 4180,
    };
    expect(collect(msg)).toEqual([
      { type: 'PAINTING_VERSION', version: ref(12, 3), stages: ['ground', 'sky'], ops: 4180 },
    ]);
  });

  it('passes init.painting through INIT', () => {
    const [action] = collect({
      type: 'init',
      strokes: [],
      gallery: [],
      status: 'idle',
      paused: true,
      piece_number: 12,
      monologue: '',
      painting: ref(12, 3),
    });
    expect(action).toMatchObject({ type: 'INIT', painting: ref(12, 3) });
  });

  it('new_canvas clears the painting', () => {
    const start = reduce(atPiece(3), { type: 'PAINTING_VERSION', version: ref(3, 1) });
    const s = collect({ type: 'new_canvas', saved_id: null }).reduce(canvasReducer, start);
    expect(s.painting).toEqual({ base: null, playing: null });
  });
});
