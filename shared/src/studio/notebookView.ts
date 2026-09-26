/**
 * Notebook display model (shared rules; the iOS client mirrors them).
 *
 * Domain tools (the server's own) keep their own lines with human labels.
 * Every other tool (SDK built-ins: Read, Write, Edit, Bash, Glob, Grep,
 * ToolSearch, TodoWrite, …) is housekeeping: each run of consecutive
 * housekeeping entries collapses into one quiet line. The stored entries are
 * untouched; this is a derived view.
 */

import type { NotebookEntry } from './notebook';

export const DOMAIN_TOOLS: ReadonlySet<string> = new Set([
  'paint',
  'critique_canvas',
  'name_piece',
  'view_canvas',
  'imagine',
  'sign_canvas',
  'mark_piece_done',
  'draw_paths',
  'generate_svg',
]);

export const isHousekeepingTool = (tool: string): boolean => !DOMAIN_TOOLS.has(tool);

type ToolEntry = Extract<NotebookEntry, { kind: 'tool' }>;

export type NotebookViewItem =
  | { kind: 'entry'; entry: NotebookEntry }
  | {
      kind: 'housekeeping';
      /** Id of the first entry in the run (stable React key). */
      id: string;
      /** Distinct lowercase tool names, first-seen order. */
      names: string[];
      entries: ToolEntry[];
    };

const isHousekeepingEntry = (entry: NotebookEntry): entry is ToolEntry =>
  entry.kind === 'tool' && isHousekeepingTool(entry.tool);

export function buildNotebookView(entries: readonly NotebookEntry[]): NotebookViewItem[] {
  const items: NotebookViewItem[] = [];
  for (const entry of entries) {
    if (!isHousekeepingEntry(entry)) {
      items.push({ kind: 'entry', entry });
      continue;
    }
    const prev = items[items.length - 1];
    const name = entry.tool.toLowerCase();
    if (prev?.kind === 'housekeeping') {
      prev.entries.push(entry);
      if (!prev.names.includes(name)) prev.names.push(name);
    } else {
      items.push({ kind: 'housekeeping', id: entry.id, names: [name], entries: [entry] });
    }
  }
  return items;
}

/** "› write · edit · bash" */
export const housekeepingLabel = (names: readonly string[]): string => `› ${names.join(' · ')}`;

const formatCount = (n: number): string => n.toLocaleString('en-US');

/** Human label for a domain tool line (without the leading "›"). */
export function toolLabel(entry: ToolEntry): string {
  switch (entry.tool) {
    case 'paint': {
      const version = entry.produced?.version ?? entry.version;
      const ops = entry.produced?.ops;
      return [
        version !== null ? `paint v${version}` : 'paint',
        ops ? `${formatCount(ops)} strokes` : null,
        entry.seconds !== null ? `${entry.seconds.toFixed(1)}s` : null,
      ]
        .filter(Boolean)
        .join(' · ');
    }
    case 'view_canvas':
      return 'looked at the canvas';
    case 'imagine':
      return 'imagined a reference';
    case 'sign_canvas':
      return 'signed the canvas';
    case 'mark_piece_done':
      return 'marked the piece done';
    case 'name_piece':
      return entry.detail ? `named it “${entry.detail}”` : 'named it';
    case 'critique_canvas':
      return 'critique';
    case 'draw_paths':
      return entry.detail ? `draw paths · ${entry.detail}` : 'draw paths';
    case 'generate_svg':
      return 'generate svg';
    default:
      return entry.tool.toLowerCase();
  }
}

// ============================================================================
// Inline markdown (critique bodies)
// ============================================================================

export interface MarkdownSpan {
  text: string;
  bold?: boolean;
  italic?: boolean;
}

export type MarkdownBlock =
  { kind: 'paragraph'; spans: MarkdownSpan[] } | { kind: 'list'; items: MarkdownSpan[][] };

/** **bold**, *italic* / _italic_; unmatched markers stay literal. */
export function parseInlineMarkdown(text: string): MarkdownSpan[] {
  const spans: MarkdownSpan[] = [];
  const pattern = /\*\*(.+?)\*\*|\*(?!\s)(.+?)\*|(?<![\w])_(?!\s)(.+?)_(?![\w])/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) spans.push({ text: text.slice(last, index) });
    if (match[1] !== undefined) spans.push({ text: match[1], bold: true });
    else spans.push({ text: (match[2] ?? match[3])!, italic: true });
    last = index + match[0].length;
  }
  if (last < text.length) spans.push({ text: text.slice(last) });
  return spans;
}

const BULLET = /^\s*[-*•]\s+/;

/** Paragraphs and "- " bullet lists with inline emphasis. */
export function parseMarkdownBlocks(text: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  let paragraph: string[] = [];
  const flush = (): void => {
    if (paragraph.length) {
      blocks.push({ kind: 'paragraph', spans: parseInlineMarkdown(paragraph.join(' ')) });
      paragraph = [];
    }
  };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    if (BULLET.test(line)) {
      flush();
      const spans = parseInlineMarkdown(line.replace(BULLET, ''));
      const prev = blocks[blocks.length - 1];
      if (prev?.kind === 'list') prev.items.push(spans);
      else blocks.push({ kind: 'list', items: [spans] });
      continue;
    }
    paragraph.push(line);
  }
  flush();
  return blocks;
}

/** "critique · pass" / "critique · fail" / "critique". */
export const critiqueLabel = (verdict: 'pass' | 'fail' | null): string =>
  verdict ? `critique · ${verdict}` : 'critique';
