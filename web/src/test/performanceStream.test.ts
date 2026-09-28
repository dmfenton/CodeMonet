/**
 * Performance stream parsing and scheduling (shared/src/renderer/performance.ts).
 */

import { describe, expect, it } from 'vitest';
import type { PerformancePatch } from '@code-monet/shared';
import {
  PerformanceParser,
  decodePatchIndex,
  patchFits,
  patchOrderThreshold,
  playbackRate,
} from '@code-monet/shared';

const part = (bytes: Uint8Array): Uint8Array => {
  const out = new Uint8Array(4 + bytes.length);
  new DataView(out.buffer).setUint32(0, bytes.length, true);
  out.set(bytes, 4);
  return out;
};
const json = (v: unknown): Uint8Array => new TextEncoder().encode(JSON.stringify(v));
const frame = (meta: unknown, index = new Uint8Array(), color = new Uint8Array()): Uint8Array => {
  const parts = [json(meta), index, color, new Uint8Array([7])].map(part);
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
};
const record = (p: PerformancePatch): Uint8Array => {
  const b = new Uint8Array(20);
  const v = new DataView(b.buffer);
  v.setFloat32(0, p.t, true);
  v.setFloat32(4, p.dur, true);
  [p.ax, p.ay, p.w, p.h, p.x, p.y].forEach((n, i) => v.setUint16(8 + i * 2, n, true));
  return b;
};

const patch: PerformancePatch = { t: 100, dur: 200, ax: 0, ay: 8, w: 16, h: 12, x: 40, y: 30 };
const stream = new Uint8Array([
  ...frame({ kind: 'header', width: 160, height: 120, format: 1 }),
  ...frame({ kind: 'chunk', stage: 'sky', atlas: [64, 32], patches: 1 }, record(patch)),
  ...frame({ kind: 'end', ms: 300 }),
]);

describe('PerformanceParser', () => {
  it('parses frames however the bytes are split', () => {
    for (const size of [1, 3, 17, stream.length]) {
      const parser = new PerformanceParser();
      const frames = [];
      for (let i = 0; i < stream.length; i += size) {
        frames.push(...parser.push(stream.subarray(i, i + size)));
      }
      expect(frames.map((f) => f.meta.kind)).toEqual(['header', 'chunk', 'end']);
      expect(decodePatchIndex(frames[1]!.index)).toEqual([patch]);
      expect(Array.from(frames[1]!.order)).toEqual([7]);
    }
  });

  it('holds back an incomplete frame', () => {
    const parser = new PerformanceParser();
    expect(parser.push(stream.subarray(0, 10))).toEqual([]);
  });
});

describe('patch scheduling', () => {
  it('reveals a patch along its draw order over [t, t + dur]', () => {
    expect(patchOrderThreshold(patch, 50)).toBe(0);
    expect(patchOrderThreshold(patch, 200)).toBeCloseTo(128);
    expect(patchOrderThreshold(patch, 300)).toBe(256);
  });

  it('skips patches outside the picture or atlases', () => {
    const picture = { width: 160, height: 120 };
    const color = { width: 64, height: 32 };
    const order = { width: 16, height: 8 };
    expect(patchFits(patch, picture, color, order)).toBe(true);
    expect(patchFits({ ...patch, x: 150 }, picture, color, order)).toBe(false);
    expect(patchFits({ ...patch, ay: 24 }, picture, color, order)).toBe(false);
    expect(patchFits({ ...patch, w: 0 }, picture, color, order)).toBe(false);
    expect(patchFits(patch, picture, color, { width: 3, height: 8 })).toBe(false);
  });
});

describe('playbackRate', () => {
  it('plays at the base rate while little is waiting', () => {
    expect(playbackRate(1, 5_000)).toBe(1);
  });

  it('slows a short stroke so it is on screen long enough to see', () => {
    // A 90 ms stroke at 3x would flash by in 30 ms; it gets 400 ms instead.
    expect(playbackRate(3, 5_000, 60_000, 90)).toBeCloseTo(90 / 400);
    // A long stroke plays at the base rate.
    expect(playbackRate(3, 5_000, 60_000, 2_000)).toBe(3);
  });

  it('catching up wins over legibility (dense paintings keep their proportions)', () => {
    expect(playbackRate(3, 1_200_000, 60_000, 30)).toBeCloseTo(20);
  });

  it('speeds up so a big backlog plays within a minute', () => {
    expect(playbackRate(1, 600_000)).toBeCloseTo(10);
    expect(playbackRate(3, 600_000, 60_000)).toBeCloseTo(10);
  });
});
