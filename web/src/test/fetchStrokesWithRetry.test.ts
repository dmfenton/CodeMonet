/**
 * fetchStrokesWithRetry Tests
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { PendingStroke } from '@code-monet/shared';
import { fetchStrokesWithRetry } from '@code-monet/shared';

const makeStroke = (batchId: number): PendingStroke => ({
  batch_id: batchId,
  path: {
    type: 'polyline',
    points: [{ x: 0, y: 0 }],
  },
  points: [{ x: 0, y: 0 }],
});

describe('fetchStrokesWithRetry', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('calls onSuccess with strokes on successful fetch', async () => {
    const strokes = [makeStroke(1)];
    const fetchFn = vi.fn().mockResolvedValue(strokes);
    const onSuccess = vi.fn();

    await fetchStrokesWithRetry({ fetchFn, onSuccess });

    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledWith(strokes);
  });

  it('retries on failure and eventually succeeds', async () => {
    const strokes = [makeStroke(2)];
    const fetchFn = vi.fn().mockRejectedValueOnce(new Error('fail')).mockResolvedValueOnce(strokes);
    const onSuccess = vi.fn();
    const onError = vi.fn();

    const promise = fetchStrokesWithRetry({
      fetchFn,
      onSuccess,
      onError,
      retryDelayMs: 100,
    });

    // First attempt fails
    await vi.advanceTimersByTimeAsync(0);
    expect(onError).toHaveBeenCalledTimes(1);

    // Wait for retry delay
    await vi.advanceTimersByTimeAsync(100);

    await promise;

    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(onSuccess).toHaveBeenCalledWith(strokes);
  });

  it('stops retrying when signal is aborted', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('fail'));
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const controller = new AbortController();

    const promise = fetchStrokesWithRetry({
      fetchFn,
      onSuccess,
      onError,
      retryDelayMs: 100,
      signal: controller.signal,
    });

    // First attempt fails
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchFn).toHaveBeenCalledTimes(1);

    // Abort during retry delay
    controller.abort();
    await vi.advanceTimersByTimeAsync(100);

    await promise;

    // Should not have retried after abort
    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('does not call onSuccess if aborted during fetch', async () => {
    const controller = new AbortController();
    const strokes = [makeStroke(3)];
    const fetchFn = vi.fn().mockImplementation(() => {
      controller.abort();
      return strokes;
    });
    const onSuccess = vi.fn();

    await fetchStrokesWithRetry({
      fetchFn,
      onSuccess,
      signal: controller.signal,
    });

    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
