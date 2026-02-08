/**
 * React hook for fetching and enqueuing pending strokes with retry.
 */

import { useEffect, useRef } from 'react';

import type { PendingStrokesInfo } from '../canvas/reducer';
import type { PendingStroke } from '../types';

const DEFAULT_RETRY_DELAY_MS = 1000;

export interface UsePendingStrokesOptions {
  pendingStrokes: PendingStrokesInfo | null;
  fetchPendingStrokes: () => Promise<PendingStroke[]>;
  enqueueStrokes: (strokes: PendingStroke[]) => void;
  clearPending: () => void;
  retryDelayMs?: number;
  onError?: (error: unknown) => void;
  connectionId?: number;
}

export function usePendingStrokes({
  pendingStrokes,
  fetchPendingStrokes,
  enqueueStrokes,
  clearPending,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  onError,
  connectionId,
}: UsePendingStrokesOptions): void {
  const lastFetchedBatchRef = useRef<number>(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset batch tracking on WS reconnection so re-sent batches are re-fetched
  useEffect(() => {
    if (connectionId !== undefined) {
      lastFetchedBatchRef.current = 0;
    }
  }, [connectionId]);

  const pendingBatchId = pendingStrokes?.batchId;

  useEffect(() => {
    if (pendingBatchId === undefined) {
      return;
    }

    if (pendingBatchId <= lastFetchedBatchRef.current) {
      return;
    }

    let cancelled = false;

    const attemptFetch = async () => {
      try {
        const strokes = await fetchPendingStrokes();
        if (cancelled) return;
        lastFetchedBatchRef.current = pendingBatchId;
        enqueueStrokes(strokes);
        clearPending();
      } catch (error) {
        if (cancelled) return;
        onError?.(error);
        retryTimeoutRef.current = setTimeout(attemptFetch, retryDelayMs);
      }
    };

    attemptFetch();

    return () => {
      cancelled = true;
      if (retryTimeoutRef.current !== null) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
    };
  }, [
    pendingBatchId,
    fetchPendingStrokes,
    enqueueStrokes,
    clearPending,
    retryDelayMs,
    onError,
  ]);
}
