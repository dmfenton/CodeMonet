/**
 * HeroPainting — theatrical replay of a real Code Monet artwork being
 * painted, stroke by stroke, with the production stamp renderer.
 *
 * Entirely deterministic: it fetches recorded stroke data (a JSON export
 * of an actual piece) and performs it. No model calls, no randomness that
 * matters — the same painting, painted live, every time.
 */

import React, { useEffect, useRef, useState } from 'react';
import type { Path } from '@code-monet/shared';
import { computeStrokeStamps, mulberry32, samplePathPoints } from '@code-monet/shared';
import type { Stamp } from '@code-monet/shared';

import { drawStampsToContext } from '../../renderers/stampSprites';

const HERO_PIECE_URL = '/hero/poplars-at-dusk.json';
const HERO_TITLE = 'Poplars at Dusk';

/** Painting phases: caption + tempo, keyed to fraction of strokes done.
 * Boundaries measured from the piece's recorded stroke order. */
const PHASES: { at: number; label: string; speed: number }[] = [
  { at: 0.0, label: 'flooding the canvas with dusk…', speed: 1.7 },
  { at: 0.05, label: 'a low sun, barely holding…', speed: 0.9 },
  { at: 0.13, label: 'the far bank settles in…', speed: 1.2 },
  { at: 0.22, label: 'four poplars rise against the light…', speed: 0.8 },
  { at: 0.53, label: "the water takes the sky's color…", speed: 1.6 },
  { at: 0.84, label: 'the trees fall into the river…', speed: 0.95 },
  { at: 0.96, label: 'last sparks on the water…', speed: 0.5 },
];

const BASE_STAMPS_PER_FRAME = 7;
const FILL_FADE_FRAMES = 14;
const START_DELAY_MS = 900;
const END_HOLD_MS = 4200;
const RASTER_SCALE = 1.5;

interface HeroPiece {
  width: number;
  height: number;
  paths: Path[];
}

type PlanElement =
  | { kind: 'fill'; path: Path; d: string }
  | { kind: 'stroke'; stamps: Stamp[]; brush: Path['brush']; color: string };

function buildPlan(piece: HeroPiece): PlanElement[] {
  const plan: PlanElement[] = [];
  for (const path of piece.paths) {
    const color = path.color ?? '#1a1a2e';
    if (path.fill && path.type === 'svg' && path.d) {
      plan.push({ kind: 'fill', path, d: path.d });
      continue;
    }
    const width = path.stroke_width ?? 3;
    if (width <= 0) continue;
    if (path.type === 'svg') {
      // Rare: stroked svg path — treat as a fill-style reveal.
      if (path.d) plan.push({ kind: 'fill', path, d: path.d });
      continue;
    }
    const points = samplePathPoints(path);
    if (points.length < 2) continue;
    const stamps = computeStrokeStamps(
      points,
      { color, strokeWidth: width, opacity: path.opacity ?? 1 },
      path.brush
    );
    if (stamps.length > 0) {
      plan.push({ kind: 'stroke', stamps, brush: path.brush, color });
    }
  }
  return plan;
}

function drawFill(ctx: CanvasRenderingContext2D, element: { path: Path; d: string }, alpha: number): void {
  const fillColor = element.path.fill ?? element.path.color ?? '#888888';
  ctx.save();
  ctx.globalAlpha = (element.path.fill_opacity ?? element.path.opacity ?? 1) * alpha;
  ctx.fillStyle = fillColor;
  ctx.fill(new Path2D(element.d));
  ctx.restore();
}

function phaseFor(fraction: number): { label: string; speed: number } {
  let current = PHASES[0]!;
  for (const phase of PHASES) {
    if (fraction >= phase.at) current = phase;
  }
  return current;
}

export function HeroPainting(): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [caption, setCaption] = useState('');
  const [typed, setTyped] = useState('');
  const [finished, setFinished] = useState(false);
  const [fading, setFading] = useState(false);

  // Typewriter for the active phase caption.
  useEffect(() => {
    setTyped('');
    if (!caption) return;
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setTyped(caption.slice(0, i));
      if (i >= caption.length) clearInterval(interval);
    }, 28);
    return (): void => clearInterval(interval);
  }, [caption]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let cancelled = false;
    let raf = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const run = async (): Promise<void> => {
      const response = await fetch(HERO_PIECE_URL);
      if (!response.ok || cancelled) return;
      const piece = (await response.json()) as HeroPiece;
      const plan = buildPlan(piece);
      const totalStamps = plan.reduce(
        (sum, el) => sum + (el.kind === 'stroke' ? el.stamps.length : 0),
        0
      );

      canvas.width = piece.width * RASTER_SCALE;
      canvas.height = piece.height * RASTER_SCALE;
      const visible = canvas.getContext('2d');
      const committedCanvas = document.createElement('canvas');
      committedCanvas.width = canvas.width;
      committedCanvas.height = canvas.height;
      const committed = committedCanvas.getContext('2d');
      if (!visible || !committed) return;
      committed.setTransform(RASTER_SCALE, 0, 0, RASTER_SCALE, 0, 0);

      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (reduceMotion) {
        for (const el of plan) {
          if (el.kind === 'fill') drawFill(committed, el, 1);
          else drawStampsToContext(committed, el.stamps, el.brush, el.stamps.length);
        }
        visible.drawImage(committedCanvas, 0, 0);
        setFinished(true);
        return;
      }

      // Playback state
      const rng = mulberry32(42);
      let elementIndex = 0;
      let progress = 0; // stamps revealed (stroke) or frames elapsed (fill)
      let pauseFrames = Math.round(START_DELAY_MS / 16.7);
      let stampsDone = 0;

      const frame = (): void => {
        if (cancelled) return;

        if (pauseFrames > 0) {
          pauseFrames--;
          raf = requestAnimationFrame(frame);
          return;
        }

        if (elementIndex >= plan.length) {
          setCaption('');
          setFinished(true);
          timer = setTimeout(() => {
            if (cancelled) return;
            setFading(true);
            timer = setTimeout(() => {
              if (cancelled) return;
              // Reset for the next performance.
              committed.save();
              committed.setTransform(1, 0, 0, 1, 0, 0);
              committed.clearRect(0, 0, committedCanvas.width, committedCanvas.height);
              committed.restore();
              visible.clearRect(0, 0, canvas.width, canvas.height);
              elementIndex = 0;
              progress = 0;
              stampsDone = 0;
              setFinished(false);
              setFading(false);
              pauseFrames = Math.round(START_DELAY_MS / 16.7);
              raf = requestAnimationFrame(frame);
            }, 900);
          }, END_HOLD_MS);
          return;
        }

        const fraction = elementIndex / plan.length;
        const phase = phaseFor(fraction);
        setCaption(phase.label);

        const element = plan[elementIndex]!;
        // Compose: committed art + the partially-played element.
        visible.clearRect(0, 0, canvas.width, canvas.height);
        visible.drawImage(committedCanvas, 0, 0);
        visible.save();
        visible.setTransform(RASTER_SCALE, 0, 0, RASTER_SCALE, 0, 0);

        let penPosition: { x: number; y: number; color: string } | null = null;

        if (element.kind === 'fill') {
          progress++;
          drawFill(visible, element, Math.min(1, progress / FILL_FADE_FRAMES));
          if (progress >= FILL_FADE_FRAMES) {
            drawFill(committed, element, 1);
            elementIndex++;
            progress = 0;
          }
        } else {
          // The stamp budget flows across consecutive small strokes so dab
          // fields stay brisk; it stops at fills and scheduled pauses.
          let budget = Math.max(1, Math.round(BASE_STAMPS_PER_FRAME * phase.speed));
          while (budget > 0 && elementIndex < plan.length) {
            const current = plan[elementIndex]!;
            if (current.kind !== 'stroke') break;
            const step = Math.min(budget, current.stamps.length - progress);
            progress += step;
            budget -= step;
            if (progress < current.stamps.length) {
              drawStampsToContext(visible, current.stamps, current.brush, progress);
              const tip = current.stamps[Math.max(0, progress - 1)]!;
              penPosition = { x: tip.x, y: tip.y, color: current.color };
              break;
            }
            drawStampsToContext(committed, current.stamps, current.brush, current.stamps.length);
            stampsDone += current.stamps.length;
            const tip = current.stamps[current.stamps.length - 1]!;
            penPosition = { x: tip.x, y: tip.y, color: current.color };
            elementIndex++;
            progress = 0;
            // Occasionally step back and look at the whole.
            if (rng() < 0.02) {
              pauseFrames = 14 + Math.floor(rng() * 22);
              break;
            }
          }
        }

        // Brush tip indicator.
        if (penPosition) {
          visible.save();
          visible.globalAlpha = 0.85;
          visible.strokeStyle = penPosition.color;
          visible.lineWidth = 1.4;
          visible.beginPath();
          visible.arc(penPosition.x, penPosition.y, 7, 0, Math.PI * 2);
          visible.stroke();
          visible.globalAlpha = 0.95;
          visible.fillStyle = penPosition.color;
          visible.beginPath();
          visible.arc(penPosition.x, penPosition.y, 2.6, 0, Math.PI * 2);
          visible.fill();
          visible.restore();
        }

        visible.restore();
        void totalStamps;
        void stampsDone;
        raf = requestAnimationFrame(frame);
      };

      raf = requestAnimationFrame(frame);
    };

    void run();
    return (): void => {
      cancelled = true;
      cancelAnimationFrame(raf);
      if (timer) clearTimeout(timer);
    };
  }, []);

  return (
    <>
      <div className="canvas-easel">
        <div className="canvas-frame">
          <div className={`canvas-body hero-painting-stage${fading ? ' hero-painting-fading' : ''}`}>
            <canvas
              ref={canvasRef}
              className="hero-painting-canvas"
              aria-label={`${HERO_TITLE} being painted stroke by stroke`}
            />
            <div className={`hero-painting-title${finished ? ' hero-painting-title-visible' : ''}`}>
              <span className="hero-painting-title-text">{HERO_TITLE}</span>
              <span className="hero-painting-title-sub">painted live, stroke by stroke</span>
            </div>
          </div>
        </div>
      </div>
      <div className="thought-stream">
        <div className="thought-label">
          <span className="thought-dot" />
          {finished ? 'signed' : 'painting'}
        </div>
        <p className="thought-text">
          {finished ? HERO_TITLE : typed}
          <span className="cursor" />
        </p>
      </div>
    </>
  );
}
