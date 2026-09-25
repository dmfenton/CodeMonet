/**
 * Program-painting reveal scheduler and geometry (shared/src/renderer/reveal.ts).
 */

import { describe, expect, it } from 'vitest';
import type { RevealManifest, RevealOp, RevealPathSink } from '@code-monet/shared';
import {
  DEFAULT_REVEAL_PACING,
  buildRevealSchedule,
  paintingAssetUrl,
  parseRevealManifest,
  parseRevealOp,
  revealOpBounds,
  revealProgressAt,
  traceRevealOp,
} from '@code-monet/shared';

import sample from './fixtures/reveal.sample.json';

const stroke = (w = 10): RevealOp => ['s', w, 0, 0, 100, 0];
const area: RevealOp = ['a', 0, 0, 100, 100];

const manifestOf = (...kfOps: RevealOp[][]): RevealManifest => ({
  width: 1600,
  height: 1200,
  keyframes: kfOps.map((ops, i) => ({ label: `kf${i}`, image: `kf_0${i}.jpg`, ops })),
});

describe('parseRevealOp', () => {
  it('accepts stroke and area ops', () => {
    expect(parseRevealOp(['s', 4, 1, 2, 3, 4])).toEqual(['s', 4, 1, 2, 3, 4]);
    expect(parseRevealOp(['a', 0, 0, 10, 20])).toEqual(['a', 0, 0, 10, 20]);
  });

  it('normalizes inverted area rects', () => {
    expect(parseRevealOp(['a', 10, 20, 0, 0])).toEqual(['a', 0, 0, 10, 20]);
  });

  it('rejects malformed ops', () => {
    expect(parseRevealOp(['s', 4, 1])).toBeNull(); // no whole point
    expect(parseRevealOp(['s', 4, 1, 2, 3])).toBeNull(); // odd coords
    expect(parseRevealOp(['s', 0, 1, 2])).toBeNull(); // zero width
    expect(parseRevealOp(['a', 0, 0, 1])).toBeNull();
    expect(parseRevealOp(['x', 0, 0, 1, 1])).toBeNull();
    expect(parseRevealOp(['s', 4, 'a', 2])).toBeNull();
    expect(parseRevealOp('s')).toBeNull();
  });
});

describe('parseRevealManifest', () => {
  it('parses the library fixture', () => {
    const m = parseRevealManifest(sample);
    expect(m).not.toBeNull();
    expect(m!.width).toBe(1600);
    expect(m!.keyframes.map((k) => k.label)).toEqual(['ground', 'sky', 'sea', 'boat', 'sign']);
    expect(m!.keyframes[1]!.ops[0]![0]).toBe('a');
    expect(m!.keyframes[1]!.ops[1]![0]).toBe('s');
  });

  it('drops malformed ops but keeps the keyframe', () => {
    const m = parseRevealManifest({
      width: 10,
      height: 10,
      keyframes: [{ label: 'a', image: 'kf_00.jpg', ops: [['s', 1, 0, 0], ['bogus']] }],
    });
    expect(m!.keyframes[0]!.ops).toEqual([['s', 1, 0, 0]]);
  });

  it('rejects unusable manifests', () => {
    expect(parseRevealManifest(null)).toBeNull();
    expect(parseRevealManifest({ width: 0, height: 10, keyframes: [] })).toBeNull();
    expect(parseRevealManifest({ width: 10, height: 10, keyframes: [{ ops: [] }] })).toBeNull();
  });
});

describe('buildRevealSchedule', () => {
  it('uses nominal pacing when under the caps', () => {
    const s = buildRevealSchedule(manifestOf([area], [stroke(), stroke()]));
    expect(s.keyframes[0]!.endMs).toBe(250);
    expect(Array.from(s.keyframes[1]!.opEndMs)).toEqual([262, 274]);
    expect(s.totalMs).toBe(274);
  });

  it('compresses a keyframe to at most 6 s', () => {
    const ops = Array.from({ length: 1000 }, () => stroke()); // nominal 12 s
    const s = buildRevealSchedule(manifestOf(ops));
    expect(s.totalMs).toBeCloseTo(6000);
    expect(s.keyframes[0]!.opEndMs[499]).toBeCloseTo(3000);
  });

  it('compresses a version to at most 45 s', () => {
    const big = Array.from({ length: 1000 }, () => stroke());
    const s = buildRevealSchedule(manifestOf(...Array.from({ length: 10 }, () => big)));
    expect(s.totalMs).toBeCloseTo(DEFAULT_REVEAL_PACING.maxVersionMs);
    expect(s.keyframes[5]!.startMs).toBeCloseTo(22500);
  });

  it('handles keyframes without ops', () => {
    const s = buildRevealSchedule(manifestOf([], [area]));
    expect(s.keyframes[0]!.endMs).toBe(0);
    expect(s.totalMs).toBe(250);
  });

  it('paces the library fixture within the caps', () => {
    const m = parseRevealManifest(sample)!;
    const s = buildRevealSchedule(m);
    // ground 250, sky 250+36, sea 48, boat 250, sign 24
    expect(s.totalMs).toBeCloseTo(858);
  });
});

describe('revealProgressAt', () => {
  const m = manifestOf([area], [stroke(), stroke(), area]);
  const s = buildRevealSchedule(m); // kf0: 0-250; kf1: 262, 274, 524

  it('starts at keyframe 0 with an area wipe in flight', () => {
    expect(revealProgressAt(s, 0)).toEqual({
      phase: 'playing',
      keyframe: 0,
      opsDone: 0,
      active: { index: 0, progress: 0 },
    });
    const mid = revealProgressAt(s, 125);
    expect(mid.phase === 'playing' && mid.active?.progress).toBeCloseTo(0.5);
  });

  it('advances through keyframes and ops', () => {
    expect(revealProgressAt(s, 250)).toMatchObject({ keyframe: 1, opsDone: 0 });
    expect(revealProgressAt(s, 262)).toMatchObject({ keyframe: 1, opsDone: 1 });
    expect(revealProgressAt(s, 300)).toMatchObject({
      keyframe: 1,
      opsDone: 2,
      active: { index: 2 },
    });
  });

  it('is done at the end', () => {
    expect(revealProgressAt(s, 524)).toEqual({ phase: 'done' });
    expect(revealProgressAt(s, 1e9)).toEqual({ phase: 'done' });
  });

  it('is immediately done for an empty version', () => {
    expect(revealProgressAt(buildRevealSchedule(manifestOf([])), 0)).toEqual({ phase: 'done' });
  });
});

describe('footprint geometry', () => {
  const recorder = (): RevealPathSink & { calls: string[] } => {
    const calls: string[] = [];
    return {
      calls,
      moveTo: () => calls.push('moveTo'),
      lineTo: () => calls.push('lineTo'),
      arc: () => calls.push('arc'),
      rect: (...args: number[]) => calls.push(`rect ${args.join(',')}`),
      closePath: () => calls.push('closePath'),
    };
  };

  it('traces a stroke as discs plus segment quads', () => {
    const sink = recorder();
    traceRevealOp(sink, ['s', 10, 0, 0, 10, 0, 20, 0]);
    expect(sink.calls.filter((c) => c === 'arc')).toHaveLength(3);
    expect(sink.calls.filter((c) => c === 'lineTo')).toHaveLength(6);
  });

  it('traces a partial area wipe from the top', () => {
    const sink = recorder();
    traceRevealOp(sink, ['a', 0, 100, 50, 300], 0.25);
    expect(sink.calls).toEqual(['rect 0,100,50,50']);
  });

  it('pads stroke bounds by half the width', () => {
    expect(revealOpBounds(['s', 10, 0, 0, 100, 20])).toEqual({ x0: -5, y0: -5, x1: 105, y1: 25 });
    expect(revealOpBounds(area)).toEqual({ x0: 0, y0: 0, x1: 100, y1: 100 });
  });

  it('builds asset URLs', () => {
    expect(paintingAssetUrl('/api', { asset_base: '/painting-assets/u/t/' }, 'final.png')).toBe(
      '/api/painting-assets/u/t/final.png'
    );
    expect(paintingAssetUrl('http://x/', { asset_base: '/p/' }, 'reveal.json')).toBe(
      'http://x/p/reveal.json'
    );
  });
});
