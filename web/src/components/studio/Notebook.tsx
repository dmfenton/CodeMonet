/**
 * Studio notebook: the agent's thinking as prose, tool calls as mono lines,
 * critiques and the viewer's nudges as ruled blocks; nudge composer pinned
 * at the bottom.
 */

import React, { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { MarkdownSpan, NotebookEntry, StudioPhase } from '@code-monet/shared';
import {
  buildNotebookView,
  critiqueLabel,
  housekeepingLabel,
  isActivePhase,
  isHousekeepingTool,
  markdownToPlainText,
  parseMarkdownBlocks,
  toolLabel,
} from '@code-monet/shared';
import { Icon } from '../brand/Icon';

function Spans({ spans }: { spans: MarkdownSpan[] }): React.ReactElement {
  return (
    <>
      {spans.map((span, i) =>
        span.bold ? (
          <strong key={i}>{span.text}</strong>
        ) : span.italic ? (
          <em key={i}>{span.text}</em>
        ) : (
          <React.Fragment key={i}>{span.text}</React.Fragment>
        )
      )}
    </>
  );
}

function Markdown({ text }: { text: string }): React.ReactElement {
  const blocks = useMemo(() => parseMarkdownBlocks(text), [text]);
  return (
    <>
      {blocks.map((block, i) =>
        block.kind === 'list' ? (
          <ul key={i}>
            {block.items.map((item, j) => (
              <li key={j}>
                <Spans spans={item} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <Spans spans={block.spans} />
          </p>
        )
      )}
    </>
  );
}

/** Critique block: verdict label, markdown body clamped to ~4 lines. */
function Critique({
  entry,
}: {
  entry: Extract<NotebookEntry, { kind: 'critique' }>;
}): React.ReactElement {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el || expanded) return;
    const measure = (): void => setOverflows(el.scrollHeight > el.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return (): void => observer.disconnect();
  }, [entry.text, expanded]);

  return (
    <div className={`nb-block nb-critique${entry.verdict ? ` is-${entry.verdict}` : ''}`}>
      <div className="nb-block-label">{critiqueLabel(entry.verdict)}</div>
      <div ref={bodyRef} className={`nb-md${expanded ? '' : ' is-clamped'}`}>
        <Markdown text={entry.text} />
      </div>
      {(overflows || expanded) && (
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
          <span aria-hidden="true">›</span> {toolLabel(entry)}
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

/**
 * Screen-reader text for the newest settled entry (open thoughts still
 * streaming and housekeeping calls are skipped so the region stays calm).
 */
export function notebookAnnouncement(entries: readonly NotebookEntry[]): string {
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i]!;
    switch (e.kind) {
      case 'thought':
        if (e.open) continue;
        return e.text.trim().slice(0, 240);
      case 'tool':
        if (isHousekeepingTool(e.tool)) continue;
        return e.status === 'running' ? `${toolLabel(e)}…` : toolLabel(e);
      case 'critique':
        return `${critiqueLabel(e.verdict)}. ${markdownToPlainText(e.text).slice(0, 240)}`.trim();
      case 'nudge':
        return `you: ${e.text}`;
      case 'note':
        return e.tone === 'error' ? `error: ${e.text}` : 'piece finished';
    }
  }
  return '';
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
  const view = useMemo(() => buildNotebookView(entries), [entries]);
  const announcement = useMemo(() => notebookAnnouncement(entries), [entries]);
  let prevVersion: number | null = null;

  return (
    <aside className="notebook" data-testid="thinking-strip" aria-label="Notebook">
      <div className="notebook-head">
        <span className="mono-label">
          notebook{latestVersion !== null ? ` · v${latestVersion}` : ''}
        </span>
      </div>
      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
      <div className="notebook-scroll" ref={scrollRef} onScroll={handleScroll}>
        {entries.length === 0 ? (
          <p className="notebook-empty">
            {phase === 'paused' || phase === 'idle'
              ? 'The notebook fills in as the painter works.'
              : 'Listening…'}
          </p>
        ) : (
          view.map((item) => {
            if (item.kind === 'housekeeping') {
              return (
                <div
                  key={item.id}
                  className="nb-housekeeping"
                  title={`${item.entries.length} tool calls`}
                >
                  {housekeepingLabel(item.names)}
                </div>
              );
            }
            const entry = item.entry;
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
