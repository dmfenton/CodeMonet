/**
 * Shared notebook display rules: housekeeping grouping, domain tool labels,
 * critique parsing/markdown, stage bar labels vs. caption.
 */

import { describe, expect, it } from 'vitest';
import type { NotebookEntry, StageSegment } from '@code-monet/shared';
import {
  buildNotebookView,
  buildStageBar,
  critiqueLabel,
  housekeepingLabel,
  isHousekeepingTool,
  parseCritique,
  parseInlineMarkdown,
  parseMarkdownBlocks,
  parseToolSeconds,
  stageBarCaption,
  stageLabelsFit,
  toolLabel,
} from '@code-monet/shared';

type ToolEntry = Extract<NotebookEntry, { kind: 'tool' }>;

const tool = (id: string, name: string, extra: Partial<ToolEntry> = {}): ToolEntry => ({
  kind: 'tool',
  id,
  tool: name,
  iteration: 1,
  status: 'done',
  detail: null,
  version: 1,
  produced: null,
  seconds: null,
  ...extra,
});

const thought = (id: string): NotebookEntry => ({
  kind: 'thought',
  id,
  text: 'hmm',
  version: 1,
  open: false,
});

describe('housekeeping grouping', () => {
  it('classifies domain vs housekeeping tools', () => {
    for (const t of ['paint', 'critique_canvas', 'name_piece', 'view_canvas', 'imagine']) {
      expect(isHousekeepingTool(t)).toBe(false);
    }
    for (const t of ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep', 'ToolSearch', 'TodoWrite']) {
      expect(isHousekeepingTool(t)).toBe(true);
    }
  });

  it('collapses each consecutive run into one line with distinct names in order', () => {
    const entries = [
      tool('1', 'Write'),
      tool('2', 'Edit'),
      tool('3', 'Write'),
      tool('4', 'Bash'),
      tool('5', 'paint'),
      tool('6', 'Read'),
      thought('7'),
      tool('8', 'Glob'),
    ];
    const view = buildNotebookView(entries);
    expect(view.map((v) => v.kind)).toEqual([
      'housekeeping',
      'entry',
      'housekeeping',
      'entry',
      'housekeeping',
    ]);
    const first = view[0]!;
    expect(first.kind === 'housekeeping' && housekeepingLabel(first.names)).toBe(
      '› write · edit · bash'
    );
    expect(first.kind === 'housekeeping' && first.entries).toHaveLength(4);
    expect(first.kind === 'housekeeping' && first.id).toBe('1');
  });

  it('keeps every entry (derived view, no data dropped)', () => {
    const entries = [tool('1', 'Read'), tool('2', 'Read'), tool('3', 'paint')];
    const view = buildNotebookView(entries);
    const count = view.reduce((n, v) => n + (v.kind === 'housekeeping' ? v.entries.length : 1), 0);
    expect(count).toBe(entries.length);
  });
});

describe('domain tool labels', () => {
  it('labels paint with version, strokes and time', () => {
    expect(
      toolLabel(tool('p', 'paint', { produced: { version: 4, ops: 3978 }, seconds: 13 }))
    ).toBe('paint v4 · 3,978 strokes · 13.0s');
    expect(toolLabel(tool('p', 'paint', { version: 5, status: 'running' }))).toBe('paint v5');
  });

  it('uses human labels for the rest', () => {
    expect(toolLabel(tool('a', 'view_canvas'))).toBe('looked at the canvas');
    expect(toolLabel(tool('b', 'imagine'))).toBe('imagined a reference');
    expect(toolLabel(tool('c', 'sign_canvas'))).toBe('signed the canvas');
    expect(toolLabel(tool('d', 'mark_piece_done'))).toBe('marked the piece done');
    expect(toolLabel(tool('e', 'name_piece', { detail: 'Still Water' }))).toBe(
      'named it “Still Water”'
    );
  });

  it('reads the run time from paint output', () => {
    expect(parseToolSeconds('Version 3 rendered in 13.0s — 3978 recorded marks')).toBe(13);
    expect(parseToolSeconds(null)).toBeNull();
  });
});

describe('critique', () => {
  it('strips the verdict, a leading FINDINGS header and the gate text', () => {
    const { verdict, text } = parseCritique(
      '**VERDICT: PASS**\nFINDINGS:\n- Good *value* structure.\n\nFINISH GATE: OPEN. You may sign.'
    );
    expect(verdict).toBe('pass');
    expect(text).toBe('- Good *value* structure.');
    expect(critiqueLabel('pass')).toBe('critique · pass');
    expect(critiqueLabel('fail')).toBe('critique · fail');
    expect(critiqueLabel(null)).toBe('critique');
  });

  it('renders inline markdown and bullets', () => {
    expect(parseInlineMarkdown('a **b** *c* d')).toEqual([
      { text: 'a ' },
      { text: 'b', bold: true },
      { text: ' ' },
      { text: 'c', italic: true },
      { text: ' d' },
    ]);
    expect(parseInlineMarkdown('2 * 3 = 6')).toEqual([{ text: '2 * 3 = 6' }]);
    const blocks = parseMarkdownBlocks(
      'Intro line\n- one\n- **two**\n\nREQUIRED_REVISIONS:\n- fix'
    );
    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'list', 'paragraph', 'list']);
    expect(blocks[1]!.kind === 'list' && blocks[1]!.items).toHaveLength(2);
  });
});

describe('stage bar labels', () => {
  const stages = [
    'ground',
    'sky',
    'harbor',
    'boats',
    'reflections',
    'figures',
    'glaze',
    'final touches',
  ];
  const measure = (label: string): number => label.length * 7;

  it('shows per-segment labels only when every segment fits', () => {
    const three = buildStageBar(
      [
        { label: 'ground', ops: 100 },
        { label: 'sky', ops: 100 },
        { label: 'water', ops: 100 },
      ],
      null
    );
    expect(stageLabelsFit(three, 600, 4, measure)).toBe(true);
    expect(stageLabelsFit(three, 180, 4, measure)).toBe(false); // < 72px each
    const eight = buildStageBar(
      stages.map((label) => ({ label, ops: 100 })),
      null
    );
    expect(stageLabelsFit(eight, 600, 4, measure)).toBe(false);
  });

  it('captions progress while revealing and the last stage when done', () => {
    const revealing = buildStageBar(
      stages.map((label) => ({ label, ops: 100 })),
      2
    );
    expect(stageBarCaption(revealing)).toBe('stage 3 of 8 · harbor');
    const done: StageSegment[] = buildStageBar(
      stages.map((label) => ({ label, ops: 100 })),
      null
    );
    expect(stageBarCaption(done)).toBe('8 stages · final touches');
    expect(stageBarCaption([])).toBe('');
  });
});

describe('notebook after (re)connect', () => {
  it('shows the init prompt when the notebook starts empty', async () => {
    const { canvasReducer, initialState } = await import('@code-monet/shared');
    const s = canvasReducer(
      { ...initialState, pieceNumber: 3 },
      {
        type: 'INIT',
        strokes: [],
        gallery: [],
        pieceNumber: 3,
        paused: false,
        drawingStyle: 'paint',
        prompt: 'a harbor at dawn',
      }
    );
    expect(s.notebook).toMatchObject([{ kind: 'nudge', prompt: true, text: 'a harbor at dawn' }]);
  });
});
