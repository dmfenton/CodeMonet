/**
 * Studio view models: additive protocol fields, version history, notebook
 * version tagging, stage bar, titles, phase.
 */

import { describe, expect, it } from 'vitest';
import type {
  AgentMessage,
  CanvasAction,
  CanvasHookState,
  InitMessage,
  NotebookEntry,
  PaintingVersionRef,
  PaintingVersionSummary,
  ServerMessage,
} from '@code-monet/shared';
import {
  EMPTY_VERSION_HISTORY,
  STAGE_MIN_SHARE,
  buildStageBar,
  canvasReducer,
  deriveStudioPhase,
  initialState,
  notebookVersions,
  parseCritique,
  pieceDisplayTitle,
  routeMessage,
  seedVersionHistory,
  stagesFromLabels,
  stagesFromManifest,
  truncateText,
  upsertVersion,
} from '@code-monet/shared';
import sample from './fixtures/reveal.sample.json';
import { parseRevealManifest } from '@code-monet/shared';

const ref = (piece: number, version: number): PaintingVersionRef => ({
  piece_number: piece,
  version,
  asset_base: `/painting-assets/u/p${piece}v${version}/`,
  image_width: 1600,
  image_height: 1200,
});

const summary = (
  piece: number,
  version: number,
  extra: Partial<PaintingVersionSummary> = {}
): PaintingVersionSummary => ({
  version,
  asset_base: `/painting-assets/u/p${piece}v${version}/`,
  image_width: 1600,
  image_height: 1200,
  ...extra,
});

/** Route server messages through handlers + reducer, like the app does. */
const play = (state: CanvasHookState, ...messages: ServerMessage[]): CanvasHookState => {
  let s = state;
  for (const message of messages) {
    routeMessage(message, (action: CanvasAction) => {
      s = canvasReducer(s, action);
    });
  }
  return s;
};

const reduce = (state: CanvasHookState, ...actions: CanvasAction[]): CanvasHookState =>
  actions.reduce(canvasReducer, state);

const init = (fields: Partial<InitMessage> = {}): InitMessage => ({
  type: 'init',
  strokes: [],
  gallery: [],
  status: 'idle',
  paused: false,
  piece_number: 4,
  monologue: '',
  drawing_style: 'paint',
  ...fields,
});

const tool = (
  status: 'started' | 'completed',
  tool_name: string,
  extra: Partial<Extract<ServerMessage, { type: 'code_execution' }>> = {}
): ServerMessage =>
  ({
    type: 'code_execution',
    status,
    tool_name,
    tool_input: null,
    iteration: 1,
    return_code: status === 'completed' ? 0 : null,
    ...extra,
  }) as ServerMessage;

const thinking = (text: string): ServerMessage => ({ type: 'thinking_delta', text, iteration: 1 });

const versionMsg = (piece: number, version: number, ops?: number): ServerMessage => ({
  type: 'painting_version',
  ...ref(piece, version),
  stages: ['ground', 'sky'],
  ...(ops === undefined ? {} : { ops }),
});

const kinds = (entries: NotebookEntry[]): string[] => entries.map((e) => e.kind);

// ============================================================================
// Additive protocol fields
// ============================================================================

describe('init with and without additive fields', () => {
  it('reads title, prompt and version history when present', () => {
    const s = play(
      initialState,
      init({
        title: 'Poplars at dusk',
        prompt: 'poplars by a river at dusk',
        painting: {
          ...ref(4, 3),
          versions: [
            summary(4, 1, { stages: ['ground'], ops: 900 }),
            summary(4, 2, { ops: 2100 }),
            summary(4, 3, { ops: 3000 }),
          ],
          prompt: 'poplars by a river at dusk',
        },
      })
    );
    expect(s.pieceTitle).toBe('Poplars at dusk');
    expect(s.piecePrompt).toBe('poplars by a river at dusk');
    expect(s.versionHistory.piece).toBe(4);
    expect(s.versionHistory.versions.map((v) => v.version)).toEqual([1, 2, 3]);
    expect(s.versionHistory.versions[0]?.ops).toBe(900);
    // The prompt opens the notebook as a "you" entry
    expect(s.notebook).toMatchObject([{ kind: 'nudge', prompt: true }]);
  });

  it('falls back to the current version when versions are absent', () => {
    const s = play(initialState, init({ painting: ref(4, 3) }));
    expect(s.pieceTitle).toBeNull();
    expect(s.piecePrompt).toBeNull();
    expect(s.versionHistory.versions).toEqual([summary(4, 3)]);
    expect(s.notebook).toEqual([]);
  });

  it('uses painting.prompt when the top-level prompt is absent', () => {
    const s = play(initialState, init({ painting: { ...ref(4, 1), prompt: 'a lily pond' } }));
    expect(s.piecePrompt).toBe('a lily pond');
  });

  it('seeds the notebook with the server monologue', () => {
    const s = play(initialState, init({ monologue: 'Blocking in the water first.' }));
    expect(s.notebook).toMatchObject([
      { kind: 'thought', text: 'Blocking in the water first.', version: null, open: false },
    ]);
  });

  it('records painting_version ops when present and tolerates their absence', () => {
    const withOps = play(play(initialState, init()), versionMsg(4, 1, 1234));
    expect(withOps.versionHistory.versions[0]).toMatchObject({ version: 1, ops: 1234 });
    const without = play(play(initialState, init()), versionMsg(4, 1));
    expect(without.versionHistory.versions[0]?.ops).toBeUndefined();
    expect(without.versionHistory.versions[0]?.stages).toEqual(['ground', 'sky']);
  });
});

// ============================================================================
// Version history
// ============================================================================

describe('version history', () => {
  it('accumulates versions seen this session', () => {
    const s = play(
      play(initialState, init()),
      versionMsg(4, 1),
      versionMsg(4, 2),
      versionMsg(4, 3)
    );
    expect(s.versionHistory).toMatchObject({ piece: 4 });
    expect(s.versionHistory.versions.map((v) => v.version)).toEqual([1, 2, 3]);
  });

  it('ignores duplicate versions', () => {
    const s = play(play(initialState, init()), versionMsg(4, 1), versionMsg(4, 1));
    expect(s.versionHistory.versions).toHaveLength(1);
  });

  it('starts over for a new piece', () => {
    const s = play(play(initialState, init()), versionMsg(4, 1), versionMsg(5, 1));
    expect(s.versionHistory).toMatchObject({ piece: 5 });
    expect(s.versionHistory.versions.map((v) => v.version)).toEqual([1]);
  });

  it('resets on new_canvas and clear', () => {
    const painted = play(play(initialState, init()), versionMsg(4, 1));
    expect(play(painted, { type: 'new_canvas', saved_id: null }).versionHistory).toEqual(
      EMPTY_VERSION_HISTORY
    );
    expect(play(painted, { type: 'clear' }).versionHistory).toEqual(EMPTY_VERSION_HISTORY);
  });

  it('keeps versions seen this session when reconnecting to the same piece', () => {
    const s0 = play(
      play(initialState, init()),
      thinking('Working on it.'),
      versionMsg(4, 1),
      versionMsg(4, 2)
    );
    // Older server: init carries only the current version
    const s1 = play(s0, init({ painting: ref(4, 2) }));
    expect(s1.versionHistory.versions.map((v) => v.version)).toEqual([1, 2]);
    expect(s1.notebook).toBe(s0.notebook);
  });

  it('upsert keeps fields a later bare record lacks', () => {
    const h = upsertVersion(
      upsertVersion(EMPTY_VERSION_HISTORY, 4, summary(4, 1, { ops: 10, stages: ['a'] })),
      4,
      summary(4, 1)
    );
    expect(h.versions).toEqual([summary(4, 1, { ops: 10, stages: ['a'], created_at: undefined })]);
  });

  it('seed returns empty history without a painting', () => {
    const h = upsertVersion(EMPTY_VERSION_HISTORY, 4, summary(4, 1));
    expect(seedVersionHistory(h, null)).toEqual(EMPTY_VERSION_HISTORY);
  });
});

// ============================================================================
// Notebook
// ============================================================================

describe('notebook', () => {
  const painting = (): CanvasHookState => play(initialState, init());

  it('merges streamed thinking into one entry until a tool call', () => {
    const s = play(
      painting(),
      thinking('The sky '),
      thinking('carries it.'),
      tool('started', 'paint')
    );
    expect(kinds(s.notebook)).toEqual(['thought', 'tool']);
    expect(s.notebook[0]).toMatchObject({ text: 'The sky carries it.', open: false });
  });

  it('tags entries with the version they work toward', () => {
    const s = play(
      painting(),
      thinking('Blocking in.'),
      tool('started', 'paint'),
      versionMsg(4, 1, 318),
      tool('completed', 'paint'),
      thinking('Now the pads.')
    );
    expect(s.notebook).toMatchObject([
      { kind: 'thought', version: 1 },
      {
        kind: 'tool',
        tool: 'paint',
        status: 'done',
        version: 1,
        produced: { version: 1, ops: 318 },
      },
      { kind: 'thought', version: 2 },
    ]);
  });

  it('tags critiques with the version they looked at', () => {
    const s = play(
      painting(),
      versionMsg(4, 2),
      tool('started', 'critique_canvas'),
      tool('completed', 'critique_canvas', {
        stdout:
          'VERDICT: FAIL\nFINDINGS:\n- Reflections too literal.\n\nFINISH GATE: BLOCKED. Do not sign.',
      })
    );
    const critique = s.notebook[s.notebook.length - 1];
    expect(critique).toMatchObject({ kind: 'critique', verdict: 'fail', version: 2 });
    expect(critique?.kind === 'critique' && critique.text).toBe(
      '- Reflections too literal.'
    );
    // The started line became the critique block (no duplicate tool line)
    expect(kinds(s.notebook)).toEqual(['critique']);
  });

  it('ignores a duplicate completion', () => {
    const done = tool('completed', 'view_canvas');
    const s = play(painting(), tool('started', 'view_canvas'), done, done);
    expect(s.notebook).toHaveLength(1);
  });

  it('marks failed tools', () => {
    const s = play(
      painting(),
      tool('started', 'paint'),
      tool('completed', 'paint', { return_code: 1 })
    );
    expect(s.notebook[0]).toMatchObject({ kind: 'tool', status: 'failed' });
  });

  it('does not tag entries outside paint mode', () => {
    const s = play(play(initialState, init({ drawing_style: 'plotter' })), thinking('Lines.'));
    expect(s.notebook[0]).toMatchObject({ kind: 'thought', version: null });
    expect(notebookVersions(s)).toEqual({ working: null, latest: null });
  });

  it('records nudges and the new-piece prompt as "you" entries', () => {
    const s = reduce(
      painting(),
      { type: 'SET_PIECE_PROMPT', prompt: '  a foggy harbor ' },
      { type: 'ADD_NUDGE', text: 'more pink' }
    );
    expect(s.piecePrompt).toBe('a foggy harbor');
    expect(s.notebook).toMatchObject([
      { kind: 'nudge', text: 'a foggy harbor', prompt: true, version: 1 },
      { kind: 'nudge', text: 'more pink', prompt: false, version: 1 },
    ]);
  });

  it('takes the title from the agent naming the piece', () => {
    const s = play(
      painting(),
      tool('started', 'name_piece', { tool_input: { title: 'Lilies, late' } })
    );
    expect(s.pieceTitle).toBe('Lilies, late');
    expect(s.notebook[0]).toMatchObject({ kind: 'tool', detail: 'Lilies, late' });
  });

  it('adds error and piece-complete notes', () => {
    const s = play(
      painting(),
      { type: 'error', message: 'Agent crashed' },
      { type: 'piece_state', number: 4, completed: true }
    );
    expect(s.notebook).toMatchObject([
      { kind: 'note', tone: 'error', text: 'Agent crashed' },
      { kind: 'note', tone: 'done' },
    ]);
  });

  it('clears with the canvas', () => {
    const s = play(painting(), thinking('Hello.'), { type: 'clear' });
    expect(s.notebook).toEqual([]);
    expect(s.pieceTitle).toBeNull();
  });

  it('parseCritique tolerates output without a verdict', () => {
    expect(parseCritique('Looks fine.')).toEqual({ verdict: null, text: 'Looks fine.' });
  });

  it('keeps messages flowing for status derivation', () => {
    const s = play(painting(), tool('started', 'paint'));
    const last: AgentMessage | undefined = s.messages[s.messages.length - 1];
    expect(last?.type).toBe('code_execution');
  });
});

// ============================================================================
// Stage bar
// ============================================================================

describe('stage bar', () => {
  const stages = [
    { label: 'ground', ops: 1 },
    { label: 'sky', ops: 1500 },
    { label: 'water', ops: 1200 },
    { label: 'glaze', ops: 300 },
  ];

  it('sizes segments by op count with a visible floor', () => {
    const bar = buildStageBar(stages, null);
    const total = bar.reduce((sum, s) => sum + s.weight, 0);
    expect(total).toBeCloseTo(1, 6);
    const ground = bar[0]!;
    const sky = bar[1]!;
    // 1 op would be invisible; the floor keeps it at a readable share
    expect(ground.weight).toBeGreaterThan(STAGE_MIN_SHARE * 0.8);
    expect(sky.weight).toBeGreaterThan(bar[2]!.weight);
  });

  it('marks done / current / pending from the active keyframe', () => {
    expect(buildStageBar(stages, 2).map((s) => s.state)).toEqual([
      'done',
      'done',
      'current',
      'pending',
    ]);
    expect(buildStageBar(stages, null).every((s) => s.state === 'done')).toBe(true);
  });

  it('merges keyframes auto-split from one long stage', () => {
    const bar = buildStageBar(
      [
        { label: 'ground', ops: 10 },
        { label: 'sky', ops: 2500 },
        { label: 'sky', ops: 900 },
        { label: 'boat', ops: 40 },
      ],
      2
    );
    expect(bar.map((s) => [s.label, s.ops, s.state])).toEqual([
      ['ground', 10, 'done'],
      ['sky', 3400, 'current'],
      ['boat', 40, 'pending'],
    ]);
  });

  it('uses equal widths when only labels are known', () => {
    const bar = buildStageBar(stagesFromLabels(['a', 'b', 'c']), 0);
    expect(bar.map((s) => s.weight)).toEqual([1 / 3, 1 / 3, 1 / 3]);
    expect(bar.map((s) => s.state)).toEqual(['current', 'pending', 'pending']);
  });

  it('reads a real reveal.json', () => {
    const manifest = parseRevealManifest(sample);
    expect(manifest).not.toBeNull();
    const specs = stagesFromManifest(manifest!);
    expect(specs.length).toBe(manifest!.keyframes.length);
    expect(specs[0]!.ops).toBe(manifest!.keyframes[0]!.ops.length);
  });

  it('is empty without stages', () => {
    expect(buildStageBar([], null)).toEqual([]);
  });
});

// ============================================================================
// Titles and phase
// ============================================================================

describe('titles', () => {
  it('prefers title, then prompt, then piece number', () => {
    expect(pieceDisplayTitle({ title: 'Haystack', prompt: 'x', pieceNumber: 3 })).toBe('Haystack');
    expect(pieceDisplayTitle({ title: '  ', prompt: 'a small boat', pieceNumber: 3 })).toBe(
      'a small boat'
    );
    expect(pieceDisplayTitle({ title: null, prompt: null, pieceNumber: 3 })).toBe('Piece 3');
  });

  it('truncates long prompts at a word boundary', () => {
    const t = truncateText(
      'A foggy harbor at first light, with boats barely there and gulls over the water',
      40
    );
    expect(t.endsWith('…')).toBe(true);
    expect(t.length).toBeLessThanOrEqual(41);
    expect(t).not.toMatch(/\s…$/);
  });
});

describe('studio phase', () => {
  it('refines executing by the tool in flight', () => {
    expect(deriveStudioPhase('executing', 'critique_canvas')).toBe('critique');
    expect(deriveStudioPhase('executing', 'paint')).toBe('painting');
    expect(deriveStudioPhase('executing', 'view_canvas')).toBe('thinking');
    expect(deriveStudioPhase('drawing', null)).toBe('painting');
    expect(deriveStudioPhase('paused', 'paint')).toBe('paused');
    expect(deriveStudioPhase('idle', null)).toBe('idle');
  });
});
