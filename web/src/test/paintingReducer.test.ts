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

/** A version replaying its recorded stream (it did not stream live). */
const replaying = (piece: number, version: number) => {
  const v = ref(piece, version);
  return {
    ref: {
      piece_number: v.piece_number,
      asset_base: v.asset_base,
      image_width: v.image_width,
      image_height: v.image_height,
    },
    confirmed: v,
    played: false,
  };
};

describe('painting reducer', () => {
  it('performs a version that did not stream live from its recorded stream', () => {
    const s = reduce(atPiece(3), { type: 'PAINTING_VERSION', version: ref(3, 1) });
    expect(s.painting).toEqual({ base: null, live: replaying(3, 1) });
    expect(deriveAgentStatus(s)).toBe('drawing');
    expect(shouldShowIdleAnimation(s)).toBe(false);
  });

  it('settles the version as the picture when its performance ends', () => {
    const s = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'PAINTING_LIVE_DONE', assetBase: ref(3, 1).asset_base }
    );
    expect(s.painting).toEqual({ base: ref(3, 1), live: null });
    expect(deriveAgentStatus(s)).toBe('idle');
  });

  it('ignores performance-done for a version that is not performing', () => {
    const s0 = reduce(atPiece(3), { type: 'PAINTING_VERSION', version: ref(3, 2) });
    const s1 = reduce(s0, { type: 'PAINTING_LIVE_DONE', assetBase: ref(3, 1).asset_base });
    expect(s1).toBe(s0);
  });

  it('finishes the current performance when another version arrives', () => {
    const s = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'PAINTING_VERSION', version: ref(3, 2) }
    );
    expect(s.painting).toEqual({ base: ref(3, 1), live: replaying(3, 2) });
  });

  it('ignores duplicate or older versions of the same piece', () => {
    const s0 = reduce(atPiece(3), { type: 'PAINTING_VERSION', version: ref(3, 2) });
    expect(reduce(s0, { type: 'PAINTING_VERSION', version: ref(3, 1) })).toBe(s0);
    const settled = reduce(s0, { type: 'PAINTING_LIVE_DONE', assetBase: ref(3, 2).asset_base });
    expect(reduce(settled, { type: 'PAINTING_VERSION', version: ref(3, 2) })).toBe(settled);
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
      { ...atPiece(3), painting: { base: ref(3, 4), live: null } },
      { type: 'PAINTING_VERSION', version: ref(4, 1) }
    );
    expect(s.pieceNumber).toBe(4);
    expect(s.painting).toEqual({ base: null, live: replaying(4, 1) });
  });

  it('resets on CLEAR', () => {
    const s = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'CLEAR' }
    );
    expect(s.painting).toEqual({ base: null, live: null });
  });

  it('INIT shows the current version without performing it', () => {
    const s = reduce(atPiece(0), {
      type: 'INIT',
      strokes: [],
      gallery: [],
      pieceNumber: 7,
      paused: true,
      painting: ref(7, 3),
    });
    expect(s.painting).toEqual({ base: ref(7, 3), live: null });
    const none = reduce(s, {
      type: 'INIT',
      strokes: [],
      gallery: [],
      pieceNumber: 8,
      paused: true,
    });
    expect(none.painting).toEqual({ base: null, live: null });
  });

  it('hides the painting while viewing a gallery piece and restores it after', () => {
    const viewing = reduce(
      atPiece(3),
      { type: 'PAINTING_VERSION', version: ref(3, 1) },
      { type: 'LOAD_CANVAS', strokes: [], pieceNumber: 1 }
    );
    expect(viewing.painting).toEqual({ base: null, live: null });
    const back = reduce(viewing, { type: 'CLEAR_VIEWING' });
    // An in-flight performance is collapsed to its final on the way out
    expect(back.painting).toEqual({ base: ref(3, 1), live: null });
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
    expect(s.painting).toEqual({ base: null, live: null });
  });
});

describe('live painting', () => {
  const liveRef = (piece: number, version: number) => {
    const { piece_number, asset_base, image_width, image_height } = ref(piece, version);
    return { piece_number, asset_base, image_width, image_height };
  };
  const withBase = reduce(
    atPiece(3),
    { type: 'PAINTING_VERSION', version: ref(3, 1) },
    { type: 'PAINTING_LIVE_DONE', assetBase: ref(3, 1).asset_base }
  );

  it('plays a run live over the current picture', () => {
    const s = reduce(withBase, { type: 'PAINTING_LIVE', live: liveRef(3, 2) });
    expect(s.painting).toEqual({
      base: ref(3, 1),
      live: { ref: liveRef(3, 2), confirmed: null, played: false },
    });
    expect(deriveAgentStatus(s)).toBe('drawing');
  });

  it('confirms the run without replaying it, then settles when playback ends', () => {
    const s = reduce(
      withBase,
      { type: 'PAINTING_LIVE', live: liveRef(3, 2) },
      { type: 'PAINTING_VERSION', version: ref(3, 2) }
    );
    expect(s.painting.live?.confirmed).toEqual(ref(3, 2));
    expect(s.versionHistory.versions.map((v) => v.version)).toEqual([1, 2]);
    const done = reduce(s, { type: 'PAINTING_LIVE_DONE', assetBase: ref(3, 2).asset_base });
    expect(done.painting).toEqual({ base: ref(3, 2), live: null });
  });

  it('settles on confirmation when playback finished first', () => {
    const s = reduce(
      withBase,
      { type: 'PAINTING_LIVE', live: liveRef(3, 2) },
      { type: 'PAINTING_LIVE_DONE', assetBase: ref(3, 2).asset_base },
      { type: 'PAINTING_VERSION', version: ref(3, 2) }
    );
    expect(s.painting).toEqual({ base: ref(3, 2), live: null });
  });

  it('rolls back to the previous picture when the run fails', () => {
    const s = reduce(
      withBase,
      { type: 'PAINTING_LIVE', live: liveRef(3, 2) },
      { type: 'PAINTING_LIVE_FAILED', assetBase: ref(3, 2).asset_base }
    );
    expect(s.painting).toEqual({ base: ref(3, 1), live: null });
  });

  it('a new run replaces an unconfirmed one', () => {
    const s = reduce(
      withBase,
      { type: 'PAINTING_LIVE', live: liveRef(3, 2) },
      { type: 'PAINTING_LIVE', live: liveRef(3, 3) }
    );
    expect(s.painting.base).toEqual(ref(3, 1));
    expect(s.painting.live?.ref).toEqual(liveRef(3, 3));
  });

  it('routes live messages and ignores them while viewing a gallery piece', () => {
    const actions: CanvasAction[] = [];
    routeMessage({ type: 'painting_live', ...liveRef(3, 2) }, (a) => actions.push(a));
    const [started] = actions;
    const s = reduce(withBase, started!);
    expect(s.painting.live?.ref).toEqual(liveRef(3, 2));
    const viewing = { ...withBase, viewingPiece: 1 };
    expect(reduce(viewing, started!).painting).toBe(viewing.painting);
  });
});
