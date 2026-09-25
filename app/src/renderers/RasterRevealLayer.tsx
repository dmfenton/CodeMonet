/**
 * Raster layer for program painting (paint mode), Skia version.
 *
 * Shows the base image (previous version's final.png, or blank) and, while a
 * version is playing, reveals its keyframe images over the current picture
 * along the recorded brush footprints (docs/program-painting.md). Mirrors
 * web/src/renderers/RasterRevealLayer.tsx.
 *
 * Performance model: the picture accumulates in one offscreen surface owned
 * by the UI thread (GPU resources drawn by the Skia view must be created
 * there). Each animation frame draws only the ops revealed since the previous
 * frame — each stroke as a round-capped/joined stroke painted with the
 * keyframe image as its shader, each area op as a shader-filled rect — then
 * snapshots the surface into a shared value the Skia <Image> displays. No
 * React work or per-op nodes per frame; per-frame cost is proportional to the
 * newly revealed ops plus one snapshot.
 */

import React, { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import {
  FilterMode,
  Image as SkiaImage,
  MipmapMode,
  PaintStyle,
  Skia,
  StrokeCap,
  StrokeJoin,
  TileMode,
} from '@shopify/react-native-skia';
import type { SkCanvas, SkImage, SkPaint, SkSurface } from '@shopify/react-native-skia';
import { useSharedValue } from 'react-native-reanimated';
import type { SharedValue } from 'react-native-reanimated';
import { scheduleOnRN, scheduleOnUI } from 'react-native-worklets';

import type { PaintingVersionRef, RevealManifest } from '@code-monet/shared';
import {
  PAINTING_FINAL_FILE,
  PAINTING_MANIFEST_FILE,
  paintingAssetUrl,
  parseRevealManifest,
} from '@code-monet/shared';

import { OP_AREA, advanceRevealPlan, buildRevealPlan } from './revealPlan';
import type { RevealPlan, RevealSink } from './revealPlan';

/** Surface pixels per logical canvas unit (matches the web layer). */
const RASTER_SCALE = 2;

/** Soft leading edge of an area wipe, as a fraction of the rect height. */
const WIPE_FEATHER = 0.06;
const WIPE_FEATHER_ALPHA = 0.35;

const SAMPLING = { filter: FilterMode.Linear, mipmap: MipmapMode.None } as const;

// ============================================================================
// Asset loading (JS thread)
// ============================================================================

/** Encoded (lazily decoded) images; versions are immutable per URL. */
const imageCache = new Map<string, Promise<SkImage>>();
const IMAGE_CACHE_LIMIT = 24;

async function fetchImage(url: string): Promise<SkImage> {
  const data = await Skia.Data.fromURI(url);
  const image = Skia.Image.MakeImageFromEncoded(data);
  if (!image) throw new Error(`Failed to decode ${url}`);
  return image;
}

function loadImage(url: string): Promise<SkImage> {
  const cached = imageCache.get(url);
  if (cached) return cached;
  const promise = fetchImage(url);
  // Don't cache failures; a later attempt may succeed.
  promise.catch(() => imageCache.delete(url));
  imageCache.set(url, promise);
  if (imageCache.size > IMAGE_CACHE_LIMIT) {
    const oldest = imageCache.keys().next().value;
    if (oldest !== undefined) imageCache.delete(oldest);
  }
  return promise;
}

/**
 * Decode a keyframe to a raster image on the JS thread so the first reveal
 * frame of each keyframe doesn't stall the UI thread decoding a JPEG.
 * Transient per playback (not cached).
 */
function decodeForPlayback(image: SkImage): SkImage {
  try {
    return image.makeNonTextureImage() ?? image;
  } catch {
    return image;
  }
}

async function loadManifest(url: string): Promise<RevealManifest> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  const manifest = parseRevealManifest(await res.json());
  if (!manifest) throw new Error(`Invalid reveal manifest: ${url}`);
  return manifest;
}

// ============================================================================
// Drawing (UI thread worklets)
// ============================================================================

function ensureSurface(
  surfaceSV: SharedValue<SkSurface | null>,
  width: number,
  height: number,
  cpu: boolean
): SkSurface | null {
  'worklet';
  const current = surfaceSV.value;
  if (current && current.width() === width && current.height() === height) return current;
  current?.dispose();
  const surface = cpu ? Skia.Surface.Make(width, height) : Skia.Surface.MakeOffscreen(width, height);
  surfaceSV.value = surface;
  return surface;
}

/** Publish the surface to the displayed image (reusing the image wrapper). */
function present(surface: SkSurface, textureSV: SharedValue<SkImage | null>): void {
  'worklet';
  surface.flush();
  textureSV.modify(
    (previous) => surface.makeImageSnapshot(undefined, previous ?? undefined),
    true
  );
}

function drawImageFull(canvas: SkCanvas, image: SkImage, width: number, height: number): void {
  'worklet';
  canvas.drawImageRectOptions(
    image,
    Skia.XYWHRect(0, 0, image.width(), image.height()),
    Skia.XYWHRect(0, 0, width, height),
    FilterMode.Linear,
    MipmapMode.None,
    null
  );
}

/** Replace the picture with `image` (or blank) and cancel any playback. */
function showImageOnUI(
  gen: number,
  genSV: SharedValue<number>,
  surfaceSV: SharedValue<SkSurface | null>,
  textureSV: SharedValue<SkImage | null>,
  width: number,
  height: number,
  cpu: boolean,
  image: SkImage | null
): void {
  'worklet';
  genSV.value = gen;
  const surface = ensureSurface(surfaceSV, width, height, cpu);
  if (!surface) return;
  const canvas = surface.getCanvas();
  canvas.clear(Skia.Color('transparent'));
  if (image) drawImageFull(canvas, image, width, height);
  present(surface, textureSV);
}

interface RevealPaints {
  fill: SkPaint;
  stroke: SkPaint;
  feather: SkPaint;
}

/** Paints that paint a keyframe image (mapped to manifest coordinates). */
function makeRevealPaints(image: SkImage, plan: RevealPlan): RevealPaints {
  'worklet';
  const local = Skia.Matrix();
  local.scale(plan.width / image.width(), plan.height / image.height());
  const shader = image.makeShaderOptions(
    TileMode.Clamp,
    TileMode.Clamp,
    FilterMode.Linear,
    MipmapMode.None,
    local
  );
  const fill = Skia.Paint();
  fill.setAntiAlias(true);
  fill.setShader(shader);
  const stroke = fill.copy();
  stroke.setStyle(PaintStyle.Stroke);
  stroke.setStrokeCap(StrokeCap.Round);
  stroke.setStrokeJoin(StrokeJoin.Round);
  const feather = fill.copy();
  feather.setAlphaf(WIPE_FEATHER_ALPHA);
  return { fill, stroke, feather };
}

/**
 * Reveal a version over the current picture, one animation frame at a time,
 * then show its final image and report completion to the JS thread.
 */
function playOnUI(
  gen: number,
  genSV: SharedValue<number>,
  surfaceSV: SharedValue<SkSurface | null>,
  textureSV: SharedValue<SkImage | null>,
  width: number,
  height: number,
  cpu: boolean,
  plan: RevealPlan,
  images: SkImage[],
  finalImage: SkImage | null,
  onDone: (gen: number) => void
): void {
  'worklet';
  genSV.value = gen;
  const surface = ensureSurface(surfaceSV, width, height, cpu);
  if (!surface) {
    scheduleOnRN(onDone, gen);
    return;
  }
  const canvas = surface.getCanvas();
  const paints: (RevealPaints | null)[] = images.map(() => null);
  const paintsFor = (kf: number): RevealPaints => {
    let p = paints[kf];
    if (!p) {
      p = makeRevealPaints(images[kf]!, plan);
      paints[kf] = p;
    }
    return p;
  };
  const path = Skia.Path.Make();
  const { opKind, opData, opDataStart } = plan;

  const sink: RevealSink = {
    revealOps(kf, from, to) {
      const { fill, stroke } = paintsFor(kf);
      for (let i = from; i < to; i++) {
        const s = opDataStart[i]!;
        const e = opDataStart[i + 1]!;
        if (opKind[i] === OP_AREA) {
          const x0 = opData[s]!;
          const y0 = opData[s + 1]!;
          canvas.drawRect(Skia.XYWHRect(x0, y0, opData[s + 2]! - x0, opData[s + 3]! - y0), fill);
          continue;
        }
        const w = opData[s]!;
        if (e - s <= 3) {
          canvas.drawCircle(opData[s + 1]!, opData[s + 2]!, w / 2, fill);
          continue;
        }
        path.reset();
        path.moveTo(opData[s + 1]!, opData[s + 2]!);
        for (let j = s + 3; j + 1 < e; j += 2) path.lineTo(opData[j]!, opData[j + 1]!);
        stroke.setStrokeWidth(w);
        canvas.drawPath(path, stroke);
      }
    },
    settleKeyframe(kf) {
      canvas.drawRect(Skia.XYWHRect(0, 0, plan.width, plan.height), paintsFor(kf).fill);
    },
    wipeArea(kf, op, progress) {
      const { fill, feather } = paintsFor(kf);
      const s = opDataStart[op]!;
      const x0 = opData[s]!;
      const y0 = opData[s + 1]!;
      const x1 = opData[s + 2]!;
      const y1 = opData[s + 3]!;
      const h = y1 - y0;
      const edge = y0 + h * progress;
      canvas.drawRect(Skia.XYWHRect(x0, y0, x1 - x0, edge - y0), fill);
      // Feather: a translucent band below the edge; later frames overwrite it opaquely.
      const featherH = Math.min(h * WIPE_FEATHER, y1 - edge);
      if (featherH > 0) canvas.drawRect(Skia.XYWHRect(x0, edge, x1 - x0, featherH), feather);
    },
  };

  const cursor = { kf: 0, op: 0 };
  const sx = width / plan.width;
  const sy = height / plan.height;
  let start = -1;

  const frame = (timestamp: number): void => {
    if (genSV.value !== gen) return; // superseded or unmounted
    if (start < 0) start = timestamp;
    canvas.save();
    canvas.scale(sx, sy);
    const done = advanceRevealPlan(plan, cursor, timestamp - start, sink);
    canvas.restore();
    if (done && finalImage) {
      canvas.clear(Skia.Color('transparent'));
      drawImageFull(canvas, finalImage, width, height);
    }
    present(surface, textureSV);
    if (done) {
      scheduleOnRN(onDone, gen);
      return;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function disposeOnUI(surfaceSV: SharedValue<SkSurface | null>): void {
  'worklet';
  surfaceSV.value?.dispose();
  surfaceSV.value = null;
}

// ============================================================================
// Component
// ============================================================================

export interface RasterRevealLayerProps {
  apiUrl: string;
  base: PaintingVersionRef | null;
  playing: PaintingVersionRef | null;
  /** Logical canvas size (the layer fills 0,0 → width,height). */
  width: number;
  height: number;
  /** Called once a playing version is fully revealed (final image shown). */
  onPlaybackDone?: (assetBase: string) => void;
}

export function RasterRevealLayer({
  apiUrl,
  base,
  playing,
  width,
  height,
  onPlaybackDone,
}: RasterRevealLayerProps): React.ReactElement {
  const surfaceSV = useSharedValue<SkSurface | null>(null);
  const textureSV = useSharedValue<SkImage | null>(null);
  /** Generation of the UI-thread job allowed to draw; others stop. */
  const genSV = useSharedValue(0);
  const genRef = useRef(0);
  /** asset_base whose final image the surface currently shows in full ('' = blank). */
  const shownRef = useRef<string | null>(null);
  const onDoneRef = useRef(onPlaybackDone);
  onDoneRef.current = onPlaybackDone;
  // Versions are immutable per asset_base; the effect is keyed by it.
  const playingRef = useRef(playing);
  playingRef.current = playing;

  const baseKey = base?.asset_base ?? '';
  const playingKey = playing?.asset_base ?? '';
  const surfaceW = Math.max(1, Math.round(width * RASTER_SCALE));
  const surfaceH = Math.max(1, Math.round(height * RASTER_SCALE));

  // A new surface size starts blank; force the base to redraw.
  // (Declared before the draw effect so it runs first.)
  useEffect(() => {
    shownRef.current = null;
  }, [surfaceW, surfaceH]);

  useEffect(
    () => () => {
      genSV.value = 0;
      scheduleOnUI(disposeOnUI, surfaceSV);
    },
    [genSV, surfaceSV]
  );

  useEffect(() => {
    const playingRefValue = playingKey ? playingRef.current : null;
    const gen = ++genRef.current;
    const cpu = Platform.OS === 'web';
    let cancelled = false;

    const show = (image: SkImage | null): void =>
      scheduleOnUI(
        showImageOnUI,
        gen,
        genSV,
        surfaceSV,
        textureSV,
        surfaceW,
        surfaceH,
        cpu,
        image
      );

    const showBase = async (): Promise<void> => {
      if (shownRef.current === baseKey) return;
      const image = baseKey
        ? await loadImage(paintingAssetUrl(apiUrl, { asset_base: baseKey }, PAINTING_FINAL_FILE))
        : null;
      if (cancelled) return;
      show(image);
      shownRef.current = baseKey;
    };

    const finish = (ref: PaintingVersionRef, shown: boolean): void => {
      if (shown) shownRef.current = ref.asset_base;
      onDoneRef.current?.(ref.asset_base);
    };

    const play = async (ref: PaintingVersionRef): Promise<void> => {
      const url = (file: string): string => paintingAssetUrl(apiUrl, ref, file);
      const manifest = await loadManifest(url(PAINTING_MANIFEST_FILE));
      const [images, finalImage] = await Promise.all([
        Promise.all(manifest.keyframes.map((kf) => loadImage(url(kf.image)))),
        // Optional: without it the last keyframe (identical content) stays.
        loadImage(url(PAINTING_FINAL_FILE)).catch(() => null),
      ]);
      if (cancelled) return;
      const plan = buildRevealPlan(manifest);
      shownRef.current = null; // surface is mid-reveal
      const onDone = (doneGen: number): void => {
        if (cancelled || doneGen !== gen) return;
        finish(ref, true);
      };
      scheduleOnUI(
        playOnUI,
        gen,
        genSV,
        surfaceSV,
        textureSV,
        surfaceW,
        surfaceH,
        cpu,
        plan,
        images.map(decodeForPlayback),
        finalImage,
        onDone
      );
    };

    const run = async (): Promise<void> => {
      try {
        await showBase();
      } catch (error) {
        console.warn('[RasterRevealLayer] base image failed:', error);
      }
      if (cancelled || !playingRefValue) return;
      try {
        await play(playingRefValue);
      } catch (error) {
        if (cancelled) return;
        // Can't animate: show the final directly and move on.
        console.warn('[RasterRevealLayer] reveal failed, showing final:', error);
        let shown = false;
        try {
          const image = await loadImage(
            paintingAssetUrl(apiUrl, playingRefValue, PAINTING_FINAL_FILE)
          );
          if (cancelled) return;
          show(image);
          shown = true;
        } catch (finalError) {
          console.warn('[RasterRevealLayer] final image failed:', finalError);
        }
        if (cancelled) return;
        finish(playingRefValue, shown);
      }
    };

    void run();
    return (): void => {
      cancelled = true;
      // Stop any in-flight reveal now; the next job re-arms its own generation.
      genSV.value = 0;
    };
  }, [apiUrl, baseKey, playingKey, surfaceW, surfaceH, genSV, surfaceSV, textureSV]);

  return (
    <SkiaImage
      image={textureSV}
      x={0}
      y={0}
      width={width}
      height={height}
      fit="fill"
      sampling={SAMPLING}
    />
  );
}
