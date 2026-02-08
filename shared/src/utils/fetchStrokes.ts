/**
 * Fetch pending strokes with retry logic.
 * Plain async function (not a hook) for use in WS message handlers.
 */

import type { PendingStroke } from '../types';

const DEFAULT_RETRY_DELAY_MS = 1000;

export interface FetchStrokesOptions {
  fetchFn: () => Promise<PendingStroke[]>;
  onSuccess: (strokes: PendingStroke[]) => void;
  onError?: (error: unknown) => void;
  retryDelayMs?: number;
  signal?: AbortSignal;
}

/**
 * Fetch strokes, calling onSuccess on success, retrying on failure until aborted.
 */
export async function fetchStrokesWithRetry({
  fetchFn,
  onSuccess,
  onError,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  signal,
}: FetchStrokesOptions): Promise<void> {
  while (!signal?.aborted) {
    try {
      const strokes = await fetchFn();
      if (signal?.aborted) return;
      onSuccess(strokes);
      return;
    } catch (error) {
      if (signal?.aborted) return;
      onError?.(error);
      // Wait before retrying
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(resolve, retryDelayMs);
        signal?.addEventListener('abort', () => {
          clearTimeout(timeout);
          resolve();
        }, { once: true });
      });
    }
  }
}
