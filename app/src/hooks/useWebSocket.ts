/**
 * WebSocket connection management hook.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ClientMessage, ServerMessage } from '@code-monet/shared';

import { debugWS } from '../utils/debugLog';
import { tracer } from '../utils/tracing';

export interface WebSocketState {
  connected: boolean;
  error: string | null;
}

export interface UseWebSocketOptions {
  url: string;
  token?: string | null;
  onMessage: (message: ServerMessage) => void;
  onAuthError?: () => void;
  reconnectInterval?: number;
}

export interface UseWebSocketReturn {
  state: WebSocketState;
  send: (message: ClientMessage) => void;
  disconnect: () => void;
}

export function useWebSocket({
  url,
  token,
  onMessage,
  onAuthError,
  reconnectInterval = 3000,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [state, setState] = useState<WebSocketState>({
    connected: false,
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Use ref for handlers to avoid reconnecting when callbacks change
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onAuthErrorRef = useRef(onAuthError);
  onAuthErrorRef.current = onAuthError;

  const connect = useCallback(() => {
    // Don't connect without a token
    if (!token) {
      console.log('[WebSocket] No token, skipping connection');
      return;
    }

    // Don't create new connection if one already exists and is connecting/open
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.CONNECTING ||
        wsRef.current.readyState === WebSocket.OPEN)
    ) {
      console.log('[WebSocket] Already connected/connecting, skipping');
      return;
    }

    try {
      // Append token and trace ID to URL for distributed tracing
      const traceId = tracer.getTraceId();
      const wsUrl = `${url}?token=${encodeURIComponent(token)}&trace_id=${traceId}`;
      console.log('[WebSocket] Connecting to:', url);

      // Record connection attempt
      tracer.recordEvent('ws.connect', { url });
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        console.log('[WebSocket] Connected!');
        tracer.recordEvent('ws.connected');
        setState({ connected: true, error: null });
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Closed with code:', event.code, 'reason:', event.reason);
        tracer.recordEvent('ws.disconnect', {
          code: event.code,
          reason: event.reason || '',
        });

        // Only update state if this is still the current connection.
        // When token refreshes, a new WS replaces wsRef before the old
        // one's onclose fires — without this guard, the stale close event
        // would wipe the new connection's state.
        if (wsRef.current !== ws) {
          console.log(`[WebSocket] Stale close event ignored (code=${event.code}, replaced by new connection)`);
          return;
        }

        setState((prev) => ({ ...prev, connected: false }));
        wsRef.current = null;

        // Auth error codes (4001 = auth failed)
        if (event.code === 4001) {
          console.log('[WebSocket] Auth error, triggering callback');
          tracer.recordEvent('ws.auth_error');
          onAuthErrorRef.current?.();
          return; // Don't reconnect on auth errors
        }

        // Schedule reconnect for other close reasons
        reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
      };

      ws.onerror = (e) => {
        console.error('[WebSocket] Error:', e);
        tracer.recordError('ws.error', new Error('WebSocket connection error'));
        if (wsRef.current === ws) {
          setState((prev) => ({ ...prev, error: 'Connection error' }));
        }
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        if (wsRef.current !== ws) return;
        try {
          const message = JSON.parse(event.data) as ServerMessage;

          // Detailed logging for debugging
          if (message.type === 'thinking_delta') {
            const delta = message as { type: string; text: string };
            debugWS(`thinking_delta: "${delta.text.slice(0, 50)}..." (len=${delta.text.length})`);
          } else if (message.type === 'agent_strokes_ready') {
            const ready = message as { type: string; count: number; batch_id: number };
            debugWS(`agent_strokes_ready: count=${ready.count} batch=${ready.batch_id}`);
          } else if (message.type === 'code_execution') {
            const exec = message as { type: string; status: string; tool_name?: string };
            debugWS(`code_execution: ${exec.tool_name} status=${exec.status}`);
          } else {
            debugWS(`message: ${message.type}`);
          }

          onMessageRef.current(message);
        } catch (e) {
          console.error('Failed to handle message:', e, '\nData:', event.data.substring(0, 200));
          tracer.recordError(
            'ws.message_parse_error',
            e instanceof Error ? e : new Error(String(e))
          );
        }
      };

      wsRef.current = ws;
    } catch (e) {
      tracer.recordError('ws.connect_error', e instanceof Error ? e : new Error(String(e)));
      setState({ connected: false, error: 'Failed to connect' });
    }
  }, [url, token, reconnectInterval]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const send = useCallback((message: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  useEffect(() => {
    connect();
    return disconnect;
  }, [connect, disconnect]);

  return { state, send, disconnect };
}
