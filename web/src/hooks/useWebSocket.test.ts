import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useWebSocket } from './useWebSocket';

class FakeSocket {
  static instances: FakeSocket[] = [];
  static readonly OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  close(): void {}
  send(): void {}
}

describe('useWebSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeSocket);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('asks for a fresh session instead of retrying a rejected token', () => {
    const onAuthError = vi.fn();
    const onMessage = vi.fn();
    renderHook(() => useWebSocket({ onMessage, token: 'expired', onAuthError }));

    FakeSocket.instances[0]?.onclose?.({
      code: 4001,
      reason: 'Invalid or expired token',
    } as CloseEvent);
    vi.advanceTimersByTime(10_000);

    expect(onAuthError).toHaveBeenCalledTimes(1);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it('reconnects after a retriable close such as an identity outage', () => {
    const onAuthError = vi.fn();
    const onMessage = vi.fn();
    renderHook(() => useWebSocket({ onMessage, token: 'valid', onAuthError }));

    FakeSocket.instances[0]?.onclose?.({
      code: 1011,
      reason: 'Authentication unavailable',
    } as CloseEvent);
    vi.advanceTimersByTime(3_000);

    expect(onAuthError).not.toHaveBeenCalled();
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it('reconnects with the new token once the session is refreshed', () => {
    const onMessage = vi.fn();
    const onAuthError = vi.fn();
    const { rerender } = renderHook(
      ({ token }) => useWebSocket({ onMessage, token, onAuthError }),
      { initialProps: { token: 'expired' } }
    );
    FakeSocket.instances[0]?.onclose?.({ code: 4001, reason: '' } as CloseEvent);

    rerender({ token: 'refreshed' });

    expect(FakeSocket.instances.at(-1)?.url).toContain('token=refreshed');
  });

  it('ignores events from a socket it already replaced (StrictMode remount)', () => {
    const onMessage = vi.fn();
    const { result, rerender } = renderHook(({ token }) => useWebSocket({ onMessage, token }), {
      initialProps: { token: 'a' },
    });
    const first = FakeSocket.instances[0]!;
    rerender({ token: 'b' }); // closes the first socket, opens a second
    const second = FakeSocket.instances.at(-1)!;
    expect(second).not.toBe(first);

    act(() => second.onopen?.());
    expect(result.current.status).toBe('connected');

    // The superseded socket's late close must not mark the live one disconnected
    act(() => first.onclose?.({ code: 1006, reason: '' } as CloseEvent));
    vi.advanceTimersByTime(10_000);
    expect(result.current.status).toBe('connected');
    expect(FakeSocket.instances).toHaveLength(2);
  });
});
