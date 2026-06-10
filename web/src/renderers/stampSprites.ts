/**
 * Shared 2D-canvas stamp drawing: tinted sprite cache + stamp compositing.
 * Used by the studio's StampCanvasLayer and the homepage HeroPainting replay.
 */

import type { BrushName, Stamp } from '@code-monet/shared';
import { SPRITE_VARIANTS, generateSpriteAlpha } from '@code-monet/shared';

const SPRITE_CACHE_MAX = 768;

const tintedSpriteCache = new Map<string, HTMLCanvasElement>();

export function getTintedSprite(
  brush: BrushName | undefined,
  variant: number,
  r: number,
  g: number,
  b: number
): HTMLCanvasElement {
  // Quantize tint so nearby jittered colors share cache entries.
  const qr = r & 0xf8;
  const qg = g & 0xf8;
  const qb = b & 0xf8;
  const key = `${brush ?? 'default'}:${variant}:${qr},${qg},${qb}`;
  const cached = tintedSpriteCache.get(key);
  if (cached) return cached;

  const sprite = generateSpriteAlpha(brush, variant % SPRITE_VARIANTS);
  const canvas = document.createElement('canvas');
  canvas.width = sprite.width;
  canvas.height = sprite.height;
  const ctx = canvas.getContext('2d')!;
  const imageData = ctx.createImageData(sprite.width, sprite.height);
  const pixels = imageData.data;
  for (let i = 0; i < sprite.data.length; i++) {
    const a = sprite.data[i]!;
    const o = i * 4;
    pixels[o] = qr;
    pixels[o + 1] = qg;
    pixels[o + 2] = qb;
    pixels[o + 3] = Math.round(a * 255);
  }
  ctx.putImageData(imageData, 0, 0);

  if (tintedSpriteCache.size >= SPRITE_CACHE_MAX) {
    const firstKey = tintedSpriteCache.keys().next().value;
    if (firstKey !== undefined) tintedSpriteCache.delete(firstKey);
  }
  tintedSpriteCache.set(key, canvas);
  return canvas;
}

/** Draw the first `count` stamps of a stroke onto a 2D context. */
export function drawStampsToContext(
  ctx: CanvasRenderingContext2D,
  stamps: Stamp[],
  brush: BrushName | undefined,
  count: number
): void {
  const n = Math.min(count, stamps.length);
  for (let i = 0; i < n; i++) {
    const stamp = stamps[i]!;
    const sprite = getTintedSprite(brush, stamp.variant, stamp.color.r, stamp.color.g, stamp.color.b);
    ctx.save();
    ctx.globalAlpha = stamp.alpha;
    ctx.translate(stamp.x, stamp.y);
    ctx.rotate(stamp.angle);
    ctx.drawImage(sprite, -stamp.length / 2, -stamp.width / 2, stamp.length, stamp.width);
    ctx.restore();
  }
}
