/**
 * Tests for the flattened program-painting reveal plan and its per-frame
 * stepping (app/src/renderers/revealPlan.ts).
 */

import type { RevealManifest } from '@code-monet/shared';
import { buildRevealSchedule, revealProgressAt } from '@code-monet/shared';

import {
  OP_AREA,
  OP_STROKE,
  advanceRevealPlan,
  apiAssetUrl,
  buildRevealPlan,
  galleryRasterImageUrl,
} from '../renderers/revealPlan';
import type { RevealCursor, RevealSink } from '../renderers/revealPlan';

const manifest: RevealManifest = {
  width: 1600,
  height: 1200,
  keyframes: [
    {
      label: 'ground',
      image: 'kf_00.jpg',
      ops: [['a', 0, 0, 1600, 1200]],
    },
    {
      label: 'empty',
      image: 'kf_01.jpg',
      ops: [],
    },
    {
      label: 'strokes',
      image: 'kf_02.jpg',
      ops: [
        ['s', 14, 100, 100, 200, 200, 300, 250],
        ['s', 8, 50, 60],
        ['a', 10, 20, 110, 220],
      ],
    },
  ],
};

type Event =
  | { kind: 'ops'; kf: number; from: number; to: number }
  | { kind: 'settle'; kf: number }
  | { kind: 'wipe'; kf: number; op: number; progress: number };

function recordingSink(): { sink: RevealSink; events: Event[] } {
  const events: Event[] = [];
  return {
    events,
    sink: {
      revealOps: (kf, from, to) => events.push({ kind: 'ops', kf, from, to }),
      settleKeyframe: (kf) => events.push({ kind: 'settle', kf }),
      wipeArea: (kf, op, progress) => events.push({ kind: 'wipe', kf, op, progress }),
    },
  };
}

describe('buildRevealPlan', () => {
  const plan = buildRevealPlan(manifest);

  it('flattens ops across keyframes with global indices', () => {
    expect(plan.opKind).toEqual([OP_AREA, OP_STROKE, OP_STROKE, OP_AREA]);
    expect(plan.keyframes.map((k) => [k.opStart, k.opEnd])).toEqual([
      [0, 1],
      [1, 1],
      [1, 4],
    ]);
    expect(plan.keyframes.map((k) => k.image)).toEqual(['kf_00.jpg', 'kf_01.jpg', 'kf_02.jpg']);
  });

  it('stores op numbers without the op tag', () => {
    const data = (i: number) => plan.opData.slice(plan.opDataStart[i], plan.opDataStart[i + 1]);
    expect(data(0)).toEqual([0, 0, 1600, 1200]);
    expect(data(1)).toEqual([14, 100, 100, 200, 200, 300, 250]);
    expect(data(2)).toEqual([8, 50, 60]);
    expect(data(3)).toEqual([10, 20, 110, 220]);
    expect(plan.opDataStart).toHaveLength(plan.opKind.length + 1);
  });

  it('matches the shared schedule timing', () => {
    const schedule = buildRevealSchedule(manifest);
    expect(plan.totalMs).toBe(schedule.totalMs);
    const flat = schedule.keyframes.flatMap((k) => Array.from(k.opEndMs));
    expect(plan.opEndMs).toEqual(flat);
    expect(plan.keyframes.map((k) => [k.startMs, k.endMs])).toEqual(
      schedule.keyframes.map((k) => [k.startMs, k.endMs])
    );
  });
});

describe('advanceRevealPlan', () => {
  const plan = buildRevealPlan(manifest);

  it('wipes an in-flight area op without revealing it', () => {
    const { sink, events } = recordingSink();
    const cursor: RevealCursor = { kf: 0, op: 0 };
    const done = advanceRevealPlan(plan, cursor, plan.opEndMs[0]! / 2, sink);
    expect(done).toBe(false);
    expect(cursor).toEqual({ kf: 0, op: 0 });
    expect(events).toEqual([{ kind: 'wipe', kf: 0, op: 0, progress: 0.5 }]);
  });

  it('settles completed keyframes, including empty ones, in order', () => {
    const { sink, events } = recordingSink();
    const cursor: RevealCursor = { kf: 0, op: 0 };
    // Just past the first stroke of keyframe 2
    advanceRevealPlan(plan, cursor, plan.opEndMs[1]!, sink);
    expect(events).toEqual([
      { kind: 'ops', kf: 0, from: 0, to: 1 },
      { kind: 'settle', kf: 0 },
      { kind: 'settle', kf: 1 },
      { kind: 'ops', kf: 2, from: 1, to: 2 },
    ]);
    expect(cursor).toEqual({ kf: 2, op: 2 });
  });

  it('only emits newly revealed ops on subsequent frames', () => {
    const { sink, events } = recordingSink();
    const cursor: RevealCursor = { kf: 0, op: 0 };
    advanceRevealPlan(plan, cursor, plan.opEndMs[1]!, sink);
    events.length = 0;
    advanceRevealPlan(plan, cursor, plan.opEndMs[1]!, sink);
    expect(events).toEqual([]);
    advanceRevealPlan(plan, cursor, plan.opEndMs[2]!, sink);
    expect(events).toEqual([{ kind: 'ops', kf: 2, from: 2, to: 3 }]);
  });

  it('agrees with the shared revealProgressAt at every sampled time', () => {
    const schedule = buildRevealSchedule(manifest);
    const cursor: RevealCursor = { kf: 0, op: 0 };
    const { sink } = recordingSink();
    for (let t = 0; t < plan.totalMs; t += 7) {
      advanceRevealPlan(plan, cursor, t, sink);
      const p = revealProgressAt(schedule, t);
      if (p.phase !== 'playing') throw new Error('expected playing');
      expect(cursor.kf).toBe(p.keyframe);
      expect(cursor.op - plan.keyframes[cursor.kf]!.opStart).toBe(p.opsDone);
    }
  });

  it('finishes everything at the end, even when frames were skipped', () => {
    const { sink, events } = recordingSink();
    const cursor: RevealCursor = { kf: 0, op: 0 };
    const done = advanceRevealPlan(plan, cursor, plan.totalMs + 1000, sink);
    expect(done).toBe(true);
    expect(events).toEqual([
      { kind: 'ops', kf: 0, from: 0, to: 1 },
      { kind: 'settle', kf: 0 },
      { kind: 'settle', kf: 1 },
      { kind: 'ops', kf: 2, from: 1, to: 4 },
      { kind: 'settle', kf: 2 },
    ]);
  });

  it('is done immediately for a manifest without ops', () => {
    const empty = buildRevealPlan({
      width: 10,
      height: 10,
      keyframes: [{ label: '', image: 'kf_00.jpg', ops: [] }],
    });
    const { sink, events } = recordingSink();
    expect(advanceRevealPlan(empty, { kf: 0, op: 0 }, 0, sink)).toBe(true);
    expect(events).toEqual([{ kind: 'settle', kf: 0 }]);
  });
});

describe('gallery raster URLs', () => {
  it('joins API-relative paths onto the API base', () => {
    expect(apiAssetUrl('http://localhost:8000', '/painting-assets/u/t/final.png')).toBe(
      'http://localhost:8000/painting-assets/u/t/final.png'
    );
    expect(apiAssetUrl('https://monet.dmfenton.net/api/', '/painting-assets/x')).toBe(
      'https://monet.dmfenton.net/api/painting-assets/x'
    );
    expect(apiAssetUrl('http://a', 'https://cdn/x.png')).toBe('https://cdn/x.png');
  });

  it('only resolves raster pieces with an image_url', () => {
    const api = 'http://localhost:8000';
    expect(
      galleryRasterImageUrl(api, { format: 'raster', image_url: '/painting-assets/u/t/final.png' })
    ).toBe('http://localhost:8000/painting-assets/u/t/final.png');
    expect(galleryRasterImageUrl(api, { format: 'strokes', image_url: null })).toBeNull();
    expect(galleryRasterImageUrl(api, { format: 'raster', image_url: null })).toBeNull();
    expect(galleryRasterImageUrl(api, {})).toBeNull();
  });
});
