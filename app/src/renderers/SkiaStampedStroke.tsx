/**
 * Stamp-based painterly stroke for Skia (port of the server's painting.py).
 *
 * Each completed paint-mode stroke renders as one Atlas draw call: a brush
 * sprite sheet (4 texture variants, white-with-alpha) instanced per stamp
 * with RSXform transforms and per-stamp tint colors (modulate blend).
 */

import React, { useMemo, memo } from 'react';
import { Atlas, Skia, AlphaType, ColorType, rect } from '@shopify/react-native-skia';
import type { SkImage, SkRect, SkRSXform, SkColor } from '@shopify/react-native-skia';

import type { BrushName, Point, StrokeStyle } from '@code-monet/shared';
import {
  SPRITE_VARIANTS,
  computeStrokeStamps,
  generateSpriteAlpha,
} from '@code-monet/shared';

interface SpriteSheet {
  image: SkImage;
  sprites: SkRect[];
  /** sprite height in sheet pixels (across-stroke dimension) */
  spriteHeight: number;
}

const sheetCache = new Map<string, SpriteSheet | null>();

/**
 * Build (and cache) the sprite sheet for a brush: all variants stacked
 * vertically in one white-with-alpha image.
 */
function getSpriteSheet(brush: BrushName | undefined): SpriteSheet | null {
  const key = brush ?? 'default';
  const cached = sheetCache.get(key);
  if (cached !== undefined) return cached;

  const variants = [];
  let maxWidth = 0;
  let totalHeight = 0;
  for (let v = 0; v < SPRITE_VARIANTS; v++) {
    const sprite = generateSpriteAlpha(brush, v);
    variants.push(sprite);
    maxWidth = Math.max(maxWidth, sprite.width);
    totalHeight += sprite.height;
  }

  const pixels = new Uint8Array(maxWidth * totalHeight * 4);
  const sprites: SkRect[] = [];
  let yOffset = 0;
  for (const sprite of variants) {
    for (let y = 0; y < sprite.height; y++) {
      for (let x = 0; x < sprite.width; x++) {
        const a = Math.round(sprite.data[y * sprite.width + x]! * 255);
        const o = ((yOffset + y) * maxWidth + x) * 4;
        pixels[o] = 255;
        pixels[o + 1] = 255;
        pixels[o + 2] = 255;
        pixels[o + 3] = a;
      }
    }
    sprites.push(rect(0, yOffset, sprite.width, sprite.height));
    yOffset += sprite.height;
  }

  const image = Skia.Image.MakeImage(
    {
      width: maxWidth,
      height: totalHeight,
      alphaType: AlphaType.Unpremul,
      colorType: ColorType.RGBA_8888,
    },
    Skia.Data.fromBytes(pixels),
    maxWidth * 4
  );
  const sheet = image
    ? { image, sprites, spriteHeight: variants[0]!.height }
    : null;
  sheetCache.set(key, sheet);
  return sheet;
}

interface SkiaStampedStrokeProps {
  points: Point[];
  style: StrokeStyle;
  brushName?: BrushName;
}

export const SkiaStampedStroke = memo(function SkiaStampedStroke({
  points,
  style,
  brushName,
}: SkiaStampedStrokeProps): React.ReactElement | null {
  const atlas = useMemo(() => {
    const sheet = getSpriteSheet(brushName);
    if (!sheet) return null;

    const stamps = computeStrokeStamps(
      points,
      {
        color: style.color,
        strokeWidth: style.stroke_width,
        opacity: style.opacity ?? 1,
      },
      brushName
    );
    if (stamps.length === 0) return null;

    const sprites: SkRect[] = [];
    const transforms: SkRSXform[] = [];
    const colors: SkColor[] = [];
    for (const stamp of stamps) {
      const sprite = sheet.sprites[stamp.variant % sheet.sprites.length]!;
      const scale = stamp.width / sheet.spriteHeight;
      sprites.push(sprite);
      transforms.push(
        Skia.RSXformFromRadians(
          scale,
          stamp.angle,
          stamp.x,
          stamp.y,
          sprite.width / 2,
          sprite.height / 2
        )
      );
      colors.push(
        Float32Array.of(
          stamp.color.r / 255,
          stamp.color.g / 255,
          stamp.color.b / 255,
          stamp.alpha
        )
      );
    }
    return { image: sheet.image, sprites, transforms, colors };
  }, [points, style.color, style.stroke_width, style.opacity, brushName]);

  if (!atlas) return null;

  return (
    <Atlas
      image={atlas.image}
      sprites={atlas.sprites}
      transforms={atlas.transforms}
      colors={atlas.colors}
      blendMode="modulate"
    />
  );
});
