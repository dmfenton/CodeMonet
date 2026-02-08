/**
 * usePendingStrokes Hook Tests
 *
 * @jest-environment jsdom
 */

import { renderHook, act } from '@testing-library/react';
import type { PendingStroke } from '@code-monet/shared';
import { usePendingStrokes } from '@code-monet/shared';

const makeStroke = (batchId: number): PendingStroke => ({
  batch_id: batchId,
  path: {
    type: 'polyline',
    points: [{ x: 0, y: 0 }],
  },
  points: [{ x: 0, y: 0 }],
});

describe('usePendingStrokes', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('fetches and enqueues strokes, then clears pending', async () => {
    const strokes = [makeStroke(2)];
    const fetchPendingStrokes = jest.fn().mockResolvedValue(strokes);
    const enqueueStrokes = jest.fn();
    const clearPending = jest.fn();

    const pendingStrokes = { count: 1, batchId: 2, pieceNumber: 0 };

    renderHook(() =>
      usePendingStrokes({
        pendingStrokes,
        fetchPendingStrokes,
        enqueueStrokes,
        clearPending,
        retryDelayMs: 50,
      })
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchPendingStrokes).toHaveBeenCalledTimes(1);
    expect(enqueueStrokes).toHaveBeenCalledWith(strokes);
    expect(clearPending).toHaveBeenCalledTimes(1);
  });

  it('retries after a failed fetch', async () => {
    const strokes = [makeStroke(3)];
    const fetchPendingStrokes = jest
      .fn()
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce(strokes);
    const enqueueStrokes = jest.fn();
    const clearPending = jest.fn();

    const pendingStrokes = { count: 1, batchId: 3, pieceNumber: 0 };

    renderHook(() =>
      usePendingStrokes({
        pendingStrokes,
        fetchPendingStrokes,
        enqueueStrokes,
        clearPending,
        retryDelayMs: 100,
      })
    );

    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      jest.advanceTimersByTime(100);
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchPendingStrokes).toHaveBeenCalledTimes(2);
    expect(enqueueStrokes).toHaveBeenCalledWith(strokes);
    expect(clearPending).toHaveBeenCalledTimes(1);
  });

  it('re-fetches a previously fetched batch when connectionId changes', async () => {
    const strokes = [makeStroke(5)];
    const fetchPendingStrokes = jest.fn().mockResolvedValue(strokes);
    const enqueueStrokes = jest.fn();
    const clearPending = jest.fn();

    const { rerender } = renderHook(
      ({
        pendingStrokes,
        connectionId,
      }: {
        pendingStrokes: { count: number; batchId: number; pieceNumber: number } | null;
        connectionId: number;
      }) =>
        usePendingStrokes({
          pendingStrokes,
          fetchPendingStrokes,
          enqueueStrokes,
          clearPending,
          retryDelayMs: 50,
          connectionId,
        }),
      {
        initialProps: {
          pendingStrokes: { count: 1, batchId: 5, pieceNumber: 0 } as {
            count: number;
            batchId: number;
            pieceNumber: number;
          } | null,
          connectionId: 1,
        },
      }
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchPendingStrokes).toHaveBeenCalledTimes(1);

    // Simulate WS reconnection: connectionId changes, same batchId re-sent
    rerender({
      pendingStrokes: null,
      connectionId: 2,
    });
    rerender({
      pendingStrokes: { count: 1, batchId: 5, pieceNumber: 0 },
      connectionId: 2,
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchPendingStrokes).toHaveBeenCalledTimes(2);
    expect(enqueueStrokes).toHaveBeenCalledTimes(2);
  });

  it('does not refetch an already fetched batch', async () => {
    const strokes = [makeStroke(4)];
    const fetchPendingStrokes = jest.fn().mockResolvedValue(strokes);
    const enqueueStrokes = jest.fn();
    const clearPending = jest.fn();

    const { rerender } = renderHook(
      ({
        pendingStrokes,
      }: {
        pendingStrokes: { count: number; batchId: number; pieceNumber: number } | null;
      }) =>
        usePendingStrokes({
          pendingStrokes,
          fetchPendingStrokes,
          enqueueStrokes,
          clearPending,
          retryDelayMs: 50,
        }),
      {
        initialProps: {
          pendingStrokes: { count: 1, batchId: 4, pieceNumber: 0 } as {
            count: number;
            batchId: number;
            pieceNumber: number;
          } | null,
        },
      }
    );

    await act(async () => {
      await Promise.resolve();
    });

    rerender({ pendingStrokes: null });
    rerender({ pendingStrokes: { count: 1, batchId: 4, pieceNumber: 0 } });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchPendingStrokes).toHaveBeenCalledTimes(1);
  });
});
