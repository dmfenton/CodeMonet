/**
 * Studio notebook: the agent's thinking as prose, tool calls as mono lines,
 * critiques and the viewer's nudges as ruled blocks; nudge composer pinned
 * at the bottom.
 */

import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { NotebookEntry, StudioPhase } from '@code-monet/shared';
import { isActivePhase } from '@code-monet/shared';
import { Icon } from '../brand/Icon';

const TOOL_LABELS: Record<string, string> = {
  paint: 'paint',
  view_canvas: 'view canvas',
  critique_canvas: 'critique',
  imagine: 'imagine reference',
  name_piece: 'name piece',
  sign_canvas: 'sign',
  mark_piece_done: 'mark done',
  draw_paths: 'draw paths',
  generate_svg: 'generate svg',
};

/** Critiques longer than this collapse behind "more". */
const CRITIQUE_PREVIEW_CHARS = 320;

export function toolLine(entry: Extract<NotebookEntry, { kind: 'tool' }>): string {
  const label = TOOL_LABELS[entry.tool] ?? entry.tool;
  if (entry.tool === 'paint') {
    const version = entry.produced?.version ?? entry.version;
    const ops = entry.produced?.ops;
    return [
      version !== null ? `paint v${version}` : 'paint',
      ops ? `${ops.toLocaleString()} strokes` : null,
    ]
      .filter(Boolean)
      .join(' · ');
  }
  if (entry.tool === 'name_piece' && entry.detail) return `${label} · “${entry.detail}”`;
  return entry.detail ? `${label} · ${entry.detail}` : label;
}

function Critique({
  entry,
}: {
  entry: Extract<NotebookEntry, { kind: 'critique' }>;
}): React.ReactElement {
  const [expanded, setExpanded] = useState(false);
  const long = entry.text.length > CRITIQUE_PREVIEW_CHARS;
  const text =
    long && !expanded ? `${entry.text.slice(0, CRITIQUE_PREVIEW_CHARS).trimEnd()}…` : entry.text;
  const label = ['critique', entry.version !== null ? `v${entry.version}` : null, entry.verdict]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className={`nb-block nb-critique${entry.verdict ? ` is-${entry.verdict}` : ''}`}>
      <div className="nb-block-label">{label}</div>
      <p className="nb-block-text">{text}</p>
      {long && (
        <button type="button" className="nb-more" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'less' : 'more'}
        </button>
      )}
    </div>
  );
}

function Entry({
  entry,
  live,
}: {
  entry: NotebookEntry;
  /**
   * Last entry while the agent is active: a thought shows a caret, a tool
   * line shows it's running. (Built-in tools such as Read never report
   * completion, so earlier lines stop showing as running once work moves on.)
   */
  live: boolean;
}): React.ReactElement {
  switch (entry.kind) {
    case 'thought':
      return (
        <p className="nb-thought">
          {entry.text}
          {live && entry.open && <span className="nb-caret" aria-hidden="true" />}
        </p>
      );
    case 'tool':
      return (
        <div className={`nb-tool is-${entry.status}`}>
          <span aria-hidden="true">›</span> {toolLine(entry)}
          {entry.status === 'running' && live && <span className="nb-tool-running"> …</span>}
          {entry.status === 'failed' && <span className="nb-tool-failed"> · failed</span>}
        </div>
      );
    case 'critique':
      return <Critique entry={entry} />;
    case 'nudge':
      return (
        <div className="nb-block nb-nudge">
          <div className="nb-block-label">{entry.prompt ? 'you · prompt' : 'you'}</div>
          <p className="nb-block-text">{entry.text}</p>
        </div>
      );
    case 'note':
      return entry.tone === 'error' ? (
        <div className="nb-block nb-error">
          <div className="nb-block-label">error</div>
          <p className="nb-block-text">{entry.text}</p>
        </div>
      ) : (
        <div className="nb-done mono-label">— piece finished —</div>
      );
  }
}

interface NotebookProps {
  entries: NotebookEntry[];
  phase: StudioPhase;
  /** Paint mode: latest version on the easel (header tag). */
  latestVersion: number | null;
  canSend: boolean;
  onNudge: (text: string) => void;
}

export function Notebook({
  entries,
  phase,
  latestVersion,
  canSend,
  onNudge,
}: NotebookProps): React.ReactElement {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const [draft, setDraft] = useState('');

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    stickRef.current = el.scrollTop >= el.scrollHeight - el.clientHeight - 40;
  }, []);

  // Follow new entries while the reader is at the bottom.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (entries.length === 0) stickRef.current = true;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [entries]);

  const submit = useCallback(() => {
    const text = draft.trim();
    if (!text || !canSend) return;
    onNudge(text);
    setDraft('');
    stickRef.current = true;
  }, [draft, canSend, onNudge]);

  const last = entries[entries.length - 1];
  let prevVersion: number | null = null;

  return (
    <aside className="notebook" data-testid="thinking-strip" aria-label="Notebook">
      <div className="notebook-head">
        <span className="mono-label">
          notebook{latestVersion !== null ? ` · v${latestVersion}` : ''}
        </span>
      </div>
      <div className="notebook-scroll" ref={scrollRef} onScroll={handleScroll}>
        {entries.length === 0 ? (
          <p className="notebook-empty">
            {phase === 'paused' || phase === 'idle'
              ? 'The notebook fills in as the painter works.'
              : 'Listening…'}
          </p>
        ) : (
          entries.map((entry) => {
            // Critiques carry the version they looked at; they don't start a group.
            const group = entry.kind === 'critique' ? null : entry.version;
            const showDivider = group !== null && prevVersion !== null && group !== prevVersion;
            if (group !== null) prevVersion = group;
            return (
              <React.Fragment key={entry.id}>
                {showDivider && (
                  <div className="nb-divider mono-label" aria-hidden="true">
                    toward v{group}
                  </div>
                )}
                <Entry entry={entry} live={entry === last && isActivePhase(phase)} />
              </React.Fragment>
            );
          })
        )}
      </div>
      <form
        className="nudge-composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor="nudge-input" className="visually-hidden">
          Nudge the painter
        </label>
        <input
          id="nudge-input"
          type="text"
          data-testid="nudge-input"
          placeholder="Nudge the painter…"
          value={draft}
          autoComplete="off"
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="submit"
          className="nudge-send"
          data-testid="nudge-send"
          aria-label="Send nudge"
          disabled={!draft.trim() || !canSend}
        >
          <Icon name="up" />
        </button>
      </form>
    </aside>
  );
}
