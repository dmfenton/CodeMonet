/**
 * Studio notebook: the agent's activity for the piece on the easel, in order.
 *
 * Thinking streams into prose entries; tool calls become compact lines;
 * critique_canvas results become critique blocks; the viewer's prompt and
 * nudges are "you" entries. In paint mode each entry is tagged with the
 * version it worked toward (critiques: the version they looked at).
 */

import type { AgentMessage } from '../types';

export type NotebookEntry =
  | {
      kind: 'thought';
      id: string;
      text: string;
      version: number | null;
      /** Further thinking appends here until something else happens. */
      open: boolean;
    }
  | {
      kind: 'tool';
      id: string;
      tool: string;
      iteration: number;
      status: 'running' | 'done' | 'failed';
      /** Short, tool-specific detail (e.g. a piece name or path count). */
      detail: string | null;
      version: number | null;
      /** paint: the version this run produced, once the server reports it. */
      produced: { version: number; ops: number | null } | null;
      /** Run time reported in the tool's output (paint: "rendered in 13.0s"). */
      seconds: number | null;
    }
  | {
      kind: 'critique';
      id: string;
      iteration: number;
      verdict: 'pass' | 'fail' | null;
      text: string;
      version: number | null;
    }
  | { kind: 'nudge'; id: string; text: string; version: number | null; prompt: boolean }
  | {
      kind: 'note';
      id: string;
      tone: 'error' | 'done';
      text: string;
      version: number | null;
    };

export const MAX_NOTEBOOK_ENTRIES = 200;

let entryCounter = 0;
const nextId = (): string => `nb_${++entryCounter}`;

const bounded = (entries: NotebookEntry[]): NotebookEntry[] =>
  entries.length > MAX_NOTEBOOK_ENTRIES ? entries.slice(-MAX_NOTEBOOK_ENTRIES) : entries;

/** Versions an entry can be tagged with, computed by the caller from state. */
export interface NotebookVersions {
  /** Version the agent is working toward (null outside paint mode). */
  working: number | null;
  /** Latest version that exists (null when none / not paint mode). */
  latest: number | null;
}

export function appendThought(
  entries: NotebookEntry[],
  text: string,
  version: number | null
): NotebookEntry[] {
  if (!text) return entries;
  const last = entries[entries.length - 1];
  if (last?.kind === 'thought' && last.open && last.version === version) {
    return [...entries.slice(0, -1), { ...last, text: last.text + text }];
  }
  if (!text.trim()) return entries;
  return bounded([
    ...entries,
    { kind: 'thought', id: nextId(), text: text.replace(/^\s+/, ''), version, open: true },
  ]);
}

/** End the current thought so later thinking starts a new paragraph. */
export function sealThought(entries: NotebookEntry[]): NotebookEntry[] {
  const last = entries[entries.length - 1];
  if (last?.kind !== 'thought' || !last.open) return entries;
  return [...entries.slice(0, -1), { ...last, open: false }];
}

export function addNudge(
  entries: NotebookEntry[],
  text: string,
  version: number | null,
  prompt = false
): NotebookEntry[] {
  const clean = text.trim();
  if (!clean) return entries;
  return bounded([
    ...sealThought(entries),
    { kind: 'nudge', id: nextId(), text: clean, version, prompt },
  ]);
}

export function addNote(
  entries: NotebookEntry[],
  tone: 'error' | 'done',
  text: string,
  version: number | null
): NotebookEntry[] {
  return bounded([...sealThought(entries), { kind: 'note', id: nextId(), tone, text, version }]);
}

/** Split critique_canvas output into its verdict and readable findings. */
export function parseCritique(output: string): { verdict: 'pass' | 'fail' | null; text: string } {
  const match = /VERDICT:\s*(PASS|FAIL)/i.exec(output);
  const verdict = match ? (match[1]!.toLowerCase() as 'pass' | 'fail') : null;
  const text = output
    // Drop the tool's trailing gate instructions to the agent.
    .split(/\n\s*FINISH GATE:/)[0]!
    .replace(/^\s*\**VERDICT:\s*\**\s*(PASS|FAIL)\b[^\n]*\n?/im, '')
    .trim()
    // A leading "FINDINGS:" header repeats what the block label already says.
    .replace(/^\**FINDINGS:?\**\s*/i, '')
    .trim();
  return { verdict, text };
}

/** Run time from a tool's output, e.g. paint's "Version 3 rendered in 13.0s". */
export function parseToolSeconds(output: string | null | undefined): number | null {
  const match = /rendered in (\d+(?:\.\d+)?)\s*s\b/i.exec(output ?? '');
  return match ? Number(match[1]) : null;
}

function stringInput(
  input: Record<string, unknown> | null | undefined,
  key: string
): string | null {
  const value = input?.[key];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function pathCount(input: Record<string, unknown> | null | undefined): number | null {
  const paths = input?.paths;
  if (Array.isArray(paths)) return paths.length;
  if (typeof paths === 'string') {
    try {
      const parsed: unknown = JSON.parse(paths);
      return Array.isArray(parsed) ? parsed.length : null;
    } catch {
      return null;
    }
  }
  return null;
}

/** Tool-specific detail shown on the tool line. */
export function toolDetail(
  tool: string,
  input: Record<string, unknown> | null | undefined
): string | null {
  switch (tool) {
    case 'name_piece':
      return stringInput(input, 'title');
    case 'draw_paths': {
      const n = pathCount(input);
      return n === null ? null : `${n} path${n === 1 ? '' : 's'}`;
    }
    default:
      return null;
  }
}

function lastIndexWhere(
  entries: readonly NotebookEntry[],
  predicate: (entry: NotebookEntry) => boolean
): number {
  for (let i = entries.length - 1; i >= 0; i--) {
    if (predicate(entries[i]!)) return i;
  }
  return -1;
}

/** Record a code_execution message (started or completed). */
export function recordToolMessage(
  entries: NotebookEntry[],
  message: AgentMessage,
  versions: NotebookVersions
): NotebookEntry[] {
  if (message.type !== 'code_execution') return entries;
  const tool = message.metadata?.tool_name ?? 'tool';
  const iteration = message.iteration ?? 0;
  const input = message.metadata?.tool_input;

  if (message.status === 'started') {
    return bounded([
      ...sealThought(entries),
      {
        kind: 'tool',
        id: nextId(),
        tool,
        iteration,
        status: 'running',
        detail: toolDetail(tool, input),
        version: tool === 'critique_canvas' ? versions.latest : versions.working,
        produced: null,
        seconds: null,
      },
    ]);
  }

  // Completed: settle the matching started line; ignore duplicate completions.
  const index = lastIndexWhere(
    entries,
    (e) =>
      (e.kind === 'tool' && e.tool === tool && e.iteration === iteration) ||
      (e.kind === 'critique' && tool === 'critique_canvas' && e.iteration === iteration)
  );
  const match = index >= 0 ? entries[index]! : null;
  if (match && (match.kind !== 'tool' || match.status !== 'running')) return entries;

  const returnCode = message.metadata?.return_code;
  const failed = typeof returnCode === 'number' && returnCode !== 0;
  const output = message.metadata?.stdout ?? '';

  let settled: NotebookEntry;
  if (tool === 'critique_canvas' && !failed && output.trim()) {
    const { verdict, text } = parseCritique(output);
    settled = {
      kind: 'critique',
      id: match?.id ?? nextId(),
      iteration,
      verdict,
      text,
      version: match?.version ?? versions.latest,
    };
  } else if (match?.kind === 'tool') {
    settled = {
      ...match,
      status: failed ? 'failed' : 'done',
      seconds: parseToolSeconds(output) ?? match.seconds,
    };
  } else {
    settled = {
      kind: 'tool',
      id: nextId(),
      tool,
      iteration,
      status: failed ? 'failed' : 'done',
      detail: toolDetail(tool, input),
      version: versions.working,
      produced: null,
      seconds: parseToolSeconds(output),
    };
  }

  if (index >= 0) return entries.map((e, i) => (i === index ? settled : e));
  return bounded([...sealThought(entries), settled]);
}

/** A paint run produced `version`: attach it to the latest paint line without one. */
export function attachProducedVersion(
  entries: NotebookEntry[],
  version: number,
  ops: number | null
): NotebookEntry[] {
  const index = lastIndexWhere(entries, (e) => e.kind === 'tool' && e.tool === 'paint');
  const match = index >= 0 ? entries[index]! : null;
  if (match?.kind !== 'tool' || match.produced !== null) return entries;
  return entries.map((e, i) =>
    i === index ? { ...match, produced: { version, ops }, version } : e
  );
}
