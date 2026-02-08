/**
 * React hook for the Performance Model animation pipeline.
 *
 * The agent's output is a "performance" - events buffer until the stage is free,
 * then perform one at a time with animations.
 *
 * Server -> Buffer (queue) -> Stage (one item) -> UI
 *                                 ^
 *                         [stage free? -> advance]
 */

import { useEffect, useRef } from 'react';

import type { CanvasAction, PerformanceState } from '../canvas/reducer';
import type { Point, StrokeStyle } from '../types';
import { BIONIC_CHUNK_INTERVAL_MS, BIONIC_CHUNK_SIZE } from '../utils';

// Hold completed text for this duration before advancing to next chunk
const HOLD_AFTER_WORDS_MS = 800;

// Stroke animation batching constants
const MIN_POINTS_PER_FRAME = 1;
const MAX_POINTS_PER_FRAME = 8;
const TARGET_PIXELS_PER_SECOND = 300; // Visual speed constant for smooth animation

// Pen travel and easing constants
const TRAVEL_SPEED_MULTIPLIER = 2.0; // Travel moves faster than drawing
const PEN_LIFT_THRESHOLD = 2.0; // Skip travel for very close strokes (pixels)
const INTER_STROKE_PAUSE_MS = 200; // Pause between strokes
const PEN_SETTLE_DELAY_MS = 50; // Pause after pen arrives at new position
const EASE_MIN_SPEED_RATIO = 0.3; // Minimum speed at stroke start/end (fraction of max)

/** Calculate distance between two points */
function pointDistance(a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Generate an ease-in-out travel path between two points.
 * Uses quadratic ease-in-out for smooth acceleration/deceleration.
 */
function synthesizeTravelPath(start: Point, end: Point): Point[] {
  const dist = pointDistance(start, end);
  const numPoints = Math.max(2, Math.ceil(dist * 0.3));
  const points: Point[] = [];
  for (let i = 0; i <= numPoints; i++) {
    const t = i / numPoints;
    // Quadratic ease-in-out
    const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    points.push({
      x: start.x + (end.x - start.x) * eased,
      y: start.y + (end.y - start.y) * eased,
    });
  }
  return points;
}

// Hold events on stage for this duration so "executing" status is visible
const HOLD_EVENT_MS = 500;

// Maximum time to hold an event without new content (prevents stale UI)
const MAX_EVENT_HOLD_MS = 5000;

export interface UsePerformerOptions {
  /** Current performance state */
  performance: PerformanceState;
  /** Dispatch function for canvas actions */
  dispatch: (action: CanvasAction) => void;
  /** Whether animation is paused */
  paused: boolean;
  /** Whether user is in the studio (animation only runs in studio) */
  inStudio: boolean;
  /** Callback when strokes animation completes (to signal server) */
  onStrokesComplete?: (batchId: number) => void;
  /** Delay between word reveals in ms (default: BIONIC_CHUNK_INTERVAL_MS / BIONIC_CHUNK_SIZE) */
  wordDelayMs?: number;
  /** Animation frame delay in ms (default: 16.67 = 60fps) */
  frameDelayMs?: number;
}

/**
 * Hook that drives the performance animation loop.
 *
 * Watches the performance state and:
 * 1. Advances items from buffer to stage when stage is empty
 * 2. Reveals words one at a time for 'words' items
 * 3. Animates strokes point by point for 'strokes' items
 *    - With inter-stroke pauses, pen travel, and speed easing
 * 4. Instantly processes 'event' items
 * 5. Moves completed items to history
 */
export function usePerformer({
  performance,
  dispatch,
  paused,
  inStudio,
  onStrokesComplete,
  wordDelayMs = BIONIC_CHUNK_INTERVAL_MS / BIONIC_CHUNK_SIZE,
  frameDelayMs = 1000 / 60,
}: UsePerformerOptions): void {
  // Refs to track animation state
  const frameRef = useRef<number | null>(null);
  const lastWordTimeRef = useRef<number>(0);
  const lastStrokeTimeRef = useRef<number>(0);
  const strokePointIndexRef = useRef<number>(0);
  const holdStartRef = useRef<number | null>(null);
  const onStrokesCompleteRef = useRef(onStrokesComplete);

  // Pen travel and pause refs
  const travelPointsRef = useRef<Point[]>([]);
  const travelIndexRef = useRef<number>(0);
  const interStrokePauseRef = useRef<number | null>(null);
  const penSettleRef = useRef<number | null>(null);

  // Keep callback ref up to date
  useEffect(() => {
    onStrokesCompleteRef.current = onStrokesComplete;
  }, [onStrokesComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, []);

  // Main animation loop
  useEffect(() => {
    // Don't animate when paused or not in studio
    if (paused || !inStudio) {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
      return;
    }

    const animate = (time: number): void => {
      const { onStage, buffer, wordIndex, strokeIndex, travelTarget, penPosition } = performance;

      // If stage is empty, try to advance
      if (onStage === null) {
        if (buffer.length > 0) {
          dispatch({ type: 'ADVANCE_STAGE' });
          // Reset animation refs for new item
          strokePointIndexRef.current = 0;
          holdStartRef.current = null;
          travelPointsRef.current = [];
          travelIndexRef.current = 0;
          interStrokePauseRef.current = null;
          penSettleRef.current = null;
        }
        frameRef.current = requestAnimationFrame(animate);
        return;
      }

      // Process current stage item
      switch (onStage.type) {
        case 'words': {
          const words = onStage.text.split(/\s+/).filter((w) => w.length > 0);
          if (wordIndex < words.length) {
            // Still revealing words
            holdStartRef.current = null; // Reset hold timer while revealing
            // Check if enough time has passed since last word
            if (time - lastWordTimeRef.current >= wordDelayMs) {
              dispatch({ type: 'REVEAL_WORD' });
              lastWordTimeRef.current = time;
            }
          } else {
            // All words revealed - hold for a moment before advancing
            if (holdStartRef.current === null) {
              holdStartRef.current = time;
            }
            if (time - holdStartRef.current >= HOLD_AFTER_WORDS_MS) {
              holdStartRef.current = null;
              dispatch({ type: 'STAGE_COMPLETE' });
            }
          }
          break;
        }

        case 'event': {
          // Hold event on stage for minimum time so it's visible
          if (holdStartRef.current === null) {
            holdStartRef.current = time;
          }
          const holdTime = time - holdStartRef.current;
          const minHoldElapsed = holdTime >= HOLD_EVENT_MS;
          const maxHoldExceeded = holdTime >= MAX_EVENT_HOLD_MS;
          // After minimum hold, complete if there's something waiting
          // OR if max hold exceeded (prevents stale UI when agent stops)
          if (minHoldElapsed && (buffer.length > 0 || maxHoldExceeded)) {
            holdStartRef.current = null;
            dispatch({ type: 'STAGE_COMPLETE' });
          }
          break;
        }

        case 'strokes': {
          const strokes = onStage.strokes;
          const stroke = strokes[strokeIndex];

          if (stroke !== undefined) {
            // === Phase 1: INTER_STROKE_PAUSE ===
            // After STROKE_COMPLETE, pause briefly before pen travel (skip for first stroke)
            if (interStrokePauseRef.current !== null) {
              if (time - interStrokePauseRef.current >= INTER_STROKE_PAUSE_MS) {
                interStrokePauseRef.current = null;
                // After pause, initiate pen travel if needed
              } else {
                break; // Still pausing
              }
            }

            // === Phase 2: PEN_TRAVEL ===
            // Animate pen from previous position to next stroke's start
            if (travelTarget && travelPointsRef.current.length === 0 && penPosition) {
              // Initialize travel path
              const dist = pointDistance(penPosition, travelTarget);
              if (dist > PEN_LIFT_THRESHOLD) {
                travelPointsRef.current = synthesizeTravelPath(penPosition, travelTarget);
                travelIndexRef.current = 0;
              } else {
                // Close enough, skip travel
                dispatch({ type: 'PEN_TRAVEL_COMPLETE' });
              }
            }

            if (travelPointsRef.current.length > 0 && travelIndexRef.current < travelPointsRef.current.length) {
              // Animate travel
              const elapsed = time - lastStrokeTimeRef.current;
              if (elapsed >= frameDelayMs) {
                const travelSpeed = TARGET_PIXELS_PER_SECOND * TRAVEL_SPEED_MULTIPLIER;
                const targetPixels = (elapsed / 1000) * travelSpeed;

                const batchPoints: Point[] = [];
                let accDist = 0;
                let i = travelIndexRef.current;

                while (i < travelPointsRef.current.length && batchPoints.length < MAX_POINTS_PER_FRAME) {
                  const point = travelPointsRef.current[i]!;
                  if (batchPoints.length > 0) {
                    accDist += pointDistance(batchPoints[batchPoints.length - 1]!, point);
                    if (accDist > targetPixels && batchPoints.length >= MIN_POINTS_PER_FRAME) break;
                  }
                  batchPoints.push(point);
                  i++;
                }

                if (batchPoints.length > 0) {
                  dispatch({ type: 'PEN_TRAVEL_BATCH', points: batchPoints });
                  travelIndexRef.current = i;
                  lastStrokeTimeRef.current = time;
                }

                // Check if travel is complete
                if (i >= travelPointsRef.current.length) {
                  travelPointsRef.current = [];
                  travelIndexRef.current = 0;
                  dispatch({ type: 'PEN_TRAVEL_COMPLETE' });
                  // Start pen settle delay
                  penSettleRef.current = time;
                }
              }
              break; // Still traveling
            }

            // === Phase 3: PEN_SETTLE ===
            // Brief pause after pen arrives at new position
            if (penSettleRef.current !== null) {
              if (time - penSettleRef.current >= PEN_SETTLE_DELAY_MS) {
                penSettleRef.current = null;
              } else {
                break; // Still settling
              }
            }

            // === Phase 4: DRAWING ===
            const points = stroke.points;
            const pointIndex = strokePointIndexRef.current;

            if (pointIndex < points.length) {
              // Check if enough time has passed since last frame
              const elapsed = time - lastStrokeTimeRef.current;
              if (elapsed >= frameDelayMs) {
                // Speed easing: slow at start and end of stroke, fast in middle
                const progress = strokePointIndexRef.current / Math.max(1, points.length - 1);
                const easingMultiplier =
                  EASE_MIN_SPEED_RATIO +
                  (1 - EASE_MIN_SPEED_RATIO) * Math.sin(progress * Math.PI);

                // Calculate how many pixels we should cover based on elapsed time
                const targetPixels = (elapsed / 1000) * TARGET_PIXELS_PER_SECOND * easingMultiplier;

                // Batch points that fit within our target distance
                const batchPoints: Point[] = [];
                let accumulatedDistance = 0;
                let i = pointIndex;

                while (i < points.length && batchPoints.length < MAX_POINTS_PER_FRAME) {
                  const point = points[i];
                  if (point === undefined) break;

                  if (batchPoints.length > 0) {
                    const prevPoint = batchPoints[batchPoints.length - 1]!;
                    accumulatedDistance += pointDistance(prevPoint, point);

                    // Stop if we've covered enough distance (unless it's our first point)
                    if (
                      accumulatedDistance > targetPixels &&
                      batchPoints.length >= MIN_POINTS_PER_FRAME
                    ) {
                      break;
                    }
                  }

                  batchPoints.push(point);
                  i++;
                }

                if (batchPoints.length > 0) {
                  // Extract style from path for first point of stroke
                  const style: Partial<StrokeStyle> | undefined =
                    pointIndex === 0
                      ? {
                          ...(stroke.path.color !== undefined && { color: stroke.path.color }),
                          ...(stroke.path.stroke_width !== undefined && {
                            stroke_width: stroke.path.stroke_width,
                          }),
                          ...(stroke.path.opacity !== undefined && { opacity: stroke.path.opacity }),
                        }
                      : undefined;

                  // Dispatch batch of points for efficient animation
                  dispatch({
                    type: 'STROKE_PROGRESS_BATCH',
                    points: batchPoints,
                    style: Object.keys(style ?? {}).length > 0 ? style : undefined,
                  });
                  strokePointIndexRef.current = i;
                  lastStrokeTimeRef.current = time;
                }
              }
            } else {
              // === Phase 5: STROKE_COMPLETE → back to phase 1 ===
              dispatch({ type: 'STROKE_COMPLETE' });
              strokePointIndexRef.current = 0;
              // Start inter-stroke pause for the next stroke (if there is one)
              const nextStroke = strokes[strokeIndex + 1];
              if (nextStroke !== undefined) {
                interStrokePauseRef.current = time;
              }
            }
          } else {
            // All strokes done
            dispatch({ type: 'STAGE_COMPLETE' });
            // Signal server that animation is done
            const batchId = strokes[0]?.batch_id;
            if (batchId !== undefined) {
              onStrokesCompleteRef.current?.(batchId);
            }
          }
          break;
        }
      }

      frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [
    performance,
    dispatch,
    paused,
    inStudio,
    wordDelayMs,
    frameDelayMs,
  ]);
}
