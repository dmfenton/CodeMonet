/**
 * Hook that tracks newly committed strokes for a brief settling effect.
 *
 * When new strokes appear, their indices are marked as "settling" for
 * a short duration, allowing renderers to display them at reduced opacity
 * before transitioning to full opacity.
 */

import { useEffect, useRef, useState } from 'react';

/** Settling opacity for newly committed strokes */
export const SETTLE_OPACITY = 0.85;

/** Duration of settling effect in ms */
const SETTLE_DURATION_MS = 200;

/**
 * Returns a set of stroke indices that are currently settling (newly committed).
 * Renderers can use this to apply reduced opacity during the settling window.
 */
export function useSettlingStrokes(strokeCount: number): Set<number> {
  const prevStrokeCountRef = useRef(strokeCount);
  const [settlingIndices, setSettlingIndices] = useState<Set<number>>(new Set());

  useEffect(() => {
    const prevCount = prevStrokeCountRef.current;
    const newCount = strokeCount;
    prevStrokeCountRef.current = newCount;

    if (newCount > prevCount) {
      const newIndices = new Set<number>();
      for (let i = prevCount; i < newCount; i++) {
        newIndices.add(i);
      }
      setSettlingIndices(newIndices);

      const timer = setTimeout(() => {
        setSettlingIndices(new Set());
      }, SETTLE_DURATION_MS);
      return () => clearTimeout(timer);
    }
  }, [strokeCount]);

  return settlingIndices;
}
