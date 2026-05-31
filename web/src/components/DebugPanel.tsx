/**
 * Debug panel with tabs for agent state, filesystem, and message log.
 */

import React, { useState } from 'react';
import type { ServerMessage } from '@code-monet/shared';

interface DebugPanelProps {
  agent: {
    notes: string;
    monologue: string;
    status: string;
    piece_number: number;
    paused: boolean;
  } | null;
  files: Array<{ name: string; path: string; size: number; modified: string }>;
  messageLog: Array<{ timestamp: number; message: ServerMessage }>;
  onRefresh: () => void;
  onClearLog: () => void;
}

type TabId = 'agent' | 'files' | 'messages';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
  } as Intl.DateTimeFormatOptions);
}

export function DebugPanel({
  agent,
  files,
  messageLog,
  onRefresh,
  onClearLog,
}: DebugPanelProps): React.ReactElement {
  const [activeTab, setActiveTab] = useState<TabId>('agent');

  return (
    <div className="debug-panel">
      <div className="debug-tabs">
        <button
          className={`debug-tab ${activeTab === 'agent' ? 'active' : ''}`}
          onClick={() => setActiveTab('agent')}
        >
          Agent
        </button>
        <button
          className={`debug-tab ${activeTab === 'files' ? 'active' : ''}`}
          onClick={() => setActiveTab('files')}
        >
          Files
        </button>
        <button
          className={`debug-tab ${activeTab === 'messages' ? 'active' : ''}`}
          onClick={() => setActiveTab('messages')}
        >
          Messages ({messageLog.length})
        </button>
        <button className="debug-tab refresh" onClick={onRefresh} style={{ marginLeft: 'auto' }}>
          ↻
        </button>
      </div>

      <div className="debug-content">
        {activeTab === 'agent' && (
          <div className="agent-info">
            {agent ? (
              <>
                <div className="debug-row">
                  <span className="label">Status:</span>
                  <span className={`value status-${agent.status}`}>{agent.status}</span>
                  {agent.paused && <span className="badge">PAUSED</span>}
                </div>
                <div className="debug-row">
                  <span className="label">Piece Number:</span>
                  <span className="value">{agent.piece_number}</span>
                </div>
                <div className="debug-section">
                  <span className="label">Notes:</span>
                  <pre className="value notes">{agent.notes || '(empty)'}</pre>
                </div>
                <div className="debug-section">
                  <span className="label">Monologue:</span>
                  <pre className="value monologue">
                    {agent.monologue?.slice(0, 500) || '(empty)'}
                    {agent.monologue?.length > 500 && '...'}
                  </pre>
                </div>
              </>
            ) : (
              <div className="loading">Loading agent info...</div>
            )}
          </div>
        )}

        {activeTab === 'files' && (
          <div className="files-list">
            {files.length === 0 ? (
              <div className="empty">No workspace files</div>
            ) : (
              files.map((file) => (
                <div key={file.path} className="file-row">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">{formatBytes(file.size)}</span>
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === 'messages' && (
          <div className="message-log">
            <div className="log-header">
              <span>WebSocket Message Log</span>
              <button onClick={onClearLog}>Clear</button>
            </div>
            <div className="log-entries">
              {messageLog.length === 0 ? (
                <div className="empty">No messages yet</div>
              ) : (
                messageLog.map((entry, i) => (
                  <div key={i} className="log-entry">
                    <span className="log-time">{formatTime(entry.timestamp)}</span>
                    <span className={`log-type type-${entry.message.type}`}>
                      {entry.message.type}
                    </span>
                    <pre className="log-data">
                      {JSON.stringify(entry.message, null, 2).slice(0, 200)}
                    </pre>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      <style>{`
        .debug-row {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 6px 0;
        }

        .debug-section {
          margin-top: 14px;
        }

        .debug-section .label {
          display: block;
          margin-bottom: 6px;
        }

        .label {
          color: var(--text-muted);
          min-width: 100px;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .value {
          color: var(--text-primary);
        }

        .value.notes,
        .value.monologue {
          background: var(--bg-primary);
          padding: 10px 12px;
          border-radius: 8px;
          max-height: 100px;
          overflow-y: auto;
          white-space: pre-wrap;
          word-break: break-word;
          font-size: 11px;
          border: 1px solid var(--border-light);
        }

        .badge {
          padding: 3px 8px;
          background: linear-gradient(135deg, var(--warning), var(--atelier-indigo));
          color: var(--text-inverse);
          border-radius: 6px;
          font-size: 10px;
          font-weight: 600;
          letter-spacing: 0.05em;
        }

        .status-idle { color: var(--text-muted); }
        .status-thinking { color: var(--accent); }
        .status-executing { color: var(--warning); }
        .status-drawing { color: var(--success); }
        .status-paused { color: var(--text-secondary); }
        .status-error { color: var(--error); }

        .files-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .file-row {
          display: flex;
          justify-content: space-between;
          padding: 8px 12px;
          background: var(--bg-primary);
          border-radius: 8px;
          border: 1px solid var(--border-light);
        }

        .file-name {
          color: var(--text-primary);
          font-size: 12px;
        }

        .file-size {
          color: var(--text-muted);
          font-size: 11px;
        }

        .message-log {
          display: flex;
          flex-direction: column;
          height: 100%;
        }

        .log-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding-bottom: 10px;
          border-bottom: 1px solid var(--border-light);
          margin-bottom: 10px;
        }

        .log-header button {
          padding: 4px 10px;
          background: var(--bg-secondary);
          border: 1px solid var(--border);
          border-radius: 6px;
          color: var(--text-muted);
          cursor: pointer;
          font-size: 11px;
          transition: all 0.2s ease;
        }

        .log-header button:hover {
          background: var(--bg-tertiary);
          color: var(--text-secondary);
        }

        .log-entries {
          flex: 1;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .log-entry {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          padding: 8px 10px;
          background: var(--bg-primary);
          border-radius: 8px;
          font-size: 11px;
          border: 1px solid var(--border-light);
        }

        .log-time {
          color: var(--text-muted);
          font-family: 'SF Mono', 'Fira Code', monospace;
        }

        .log-type {
          padding: 2px 8px;
          border-radius: 6px;
          font-weight: 500;
          font-size: 10px;
        }

        .type-pen { background: rgba(78, 205, 196, 0.15); color: var(--success); }
        .type-thinking_delta { background: rgba(233, 69, 96, 0.15); color: var(--accent); }
        .type-status { background: rgba(255, 217, 61, 0.15); color: var(--warning); }
        .type-human_stroke { background: rgba(78, 205, 196, 0.15); color: var(--success); }
        .type-init { background: rgba(123, 104, 238, 0.15); color: var(--accent-violet); }

        .log-data {
          width: 100%;
          color: var(--text-muted);
          font-size: 10px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .empty,
        .loading {
          color: var(--text-muted);
          text-align: center;
          padding: 24px;
          font-style: italic;
        }

        .debug-tab.refresh {
          padding: 10px 14px;
        }

        .debug-tab.refresh:hover {
          color: var(--accent);
        }
      `}</style>
    </div>
  );
}
