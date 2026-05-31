/**
 * Debug data hook - fetches workspace and agent state.
 */

import { useCallback, useEffect, useState } from 'react';
import type { ServerMessage } from '@code-monet/shared';
import { getApiUrl } from '../config';

export interface WorkspaceFile {
  name: string;
  path: string;
  size: number;
  modified: string;
}

export interface AgentDebugInfo {
  notes: string;
  monologue: string;
  status: string;
  piece_number: number;
  paused: boolean;
}

export interface DebugState {
  agent: AgentDebugInfo | null;
  files: WorkspaceFile[];
  messageLog: Array<{ timestamp: number; message: ServerMessage }>;
  loading: boolean;
  error: string | null;
}

interface UseDebugOptions {
  token: string | null;
}

interface UseDebugReturn extends DebugState {
  refresh: () => Promise<void>;
  logMessage: (message: ServerMessage) => void;
  clearLog: () => void;
}

const MAX_LOG_MESSAGES = 100;

export function useDebug({ token }: UseDebugOptions): UseDebugReturn {
  const [state, setState] = useState<DebugState>({
    agent: null,
    files: [],
    messageLog: [],
    loading: false,
    error: null,
  });

  const refresh = useCallback(async () => {
    if (!token) {
      setState((s) => ({ ...s, loading: false, error: 'Not authenticated' }));
      return;
    }

    setState((s) => ({ ...s, loading: true, error: null }));

    try {
      const headers = { Authorization: `Bearer ${token}` };

      const [agentRes, workspaceRes] = await Promise.all([
        fetch(`${getApiUrl()}/debug/agent`, { headers }),
        fetch(`${getApiUrl()}/debug/workspace`, { headers }),
      ]);

      if (!agentRes.ok || !workspaceRes.ok) {
        throw new Error('Failed to fetch debug info');
      }

      const agent = await agentRes.json();
      const workspace = await workspaceRes.json();

      setState((s) => ({
        ...s,
        agent,
        files: workspace.files || [],
        loading: false,
      }));
    } catch (error) {
      setState((s) => ({
        ...s,
        loading: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  }, [token]);

  const logMessage = useCallback((message: ServerMessage) => {
    setState((s) => ({
      ...s,
      messageLog: [
        ...s.messageLog.slice(-MAX_LOG_MESSAGES + 1),
        { timestamp: Date.now(), message },
      ],
    }));
  }, []);

  const clearLog = useCallback(() => {
    setState((s) => ({ ...s, messageLog: [] }));
  }, []);

  // Initial fetch and polling
  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return (): void => clearInterval(interval);
  }, [refresh]);

  return {
    ...state,
    refresh,
    logMessage,
    clearLog,
  };
}
