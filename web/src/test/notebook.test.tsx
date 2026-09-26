/**
 * Notebook and stage bar rendering.
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { NotebookEntry } from '@code-monet/shared';
import { buildStageBar } from '@code-monet/shared';
import { Notebook, toolLine } from '../components/studio/Notebook';
import { StageBar } from '../components/studio/StageBar';

const entries: NotebookEntry[] = [
  { kind: 'nudge', id: 'a', text: 'poplars at dusk', version: 1, prompt: true },
  { kind: 'thought', id: 'b', text: 'The sky carries it.', version: 1, open: false },
  {
    kind: 'tool',
    id: 'c',
    tool: 'paint',
    iteration: 1,
    status: 'done',
    detail: null,
    version: 1,
    produced: { version: 1, ops: 318 },
  },
  {
    kind: 'critique',
    id: 'd',
    iteration: 1,
    verdict: 'fail',
    text: 'Reflections are too literal.',
    version: 1,
  },
  { kind: 'thought', id: 'e', text: 'Softening the water.', version: 2, open: true },
];

describe('Notebook', () => {
  it('renders entries with version tags and keeps the thinking-strip test id', () => {
    render(
      <Notebook entries={entries} phase="thinking" latestVersion={1} canSend onNudge={() => {}} />
    );
    expect(screen.getByTestId('thinking-strip')).toBeTruthy();
    expect(screen.getByText('notebook · v1')).toBeTruthy();
    expect(screen.getByText('you · prompt')).toBeTruthy();
    expect(screen.getByText(/paint v1 · 318 strokes/)).toBeTruthy();
    expect(screen.getByText('critique · v1 · fail')).toBeTruthy();
    expect(screen.getByText('toward v2')).toBeTruthy();
  });

  it('sends a nudge and clears the draft', () => {
    const onNudge = vi.fn();
    render(<Notebook entries={[]} phase="idle" latestVersion={null} canSend onNudge={onNudge} />);
    const input = screen.getByTestId('nudge-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'more pink' } });
    fireEvent.click(screen.getByTestId('nudge-send'));
    expect(onNudge).toHaveBeenCalledWith('more pink');
    expect(input.value).toBe('');
  });

  it('does not send while disconnected', () => {
    const onNudge = vi.fn();
    render(
      <Notebook entries={[]} phase="idle" latestVersion={null} canSend={false} onNudge={onNudge} />
    );
    fireEvent.change(screen.getByTestId('nudge-input'), { target: { value: 'hi' } });
    expect((screen.getByTestId('nudge-send') as HTMLButtonElement).disabled).toBe(true);
  });

  it('formats tool lines', () => {
    expect(
      toolLine({
        kind: 'tool',
        id: 'x',
        tool: 'paint',
        iteration: 1,
        status: 'running',
        detail: null,
        version: 3,
        produced: null,
      })
    ).toBe('paint v3');
    expect(
      toolLine({
        kind: 'tool',
        id: 'y',
        tool: 'name_piece',
        iteration: 1,
        status: 'done',
        detail: 'Haystack',
        version: null,
        produced: null,
      })
    ).toBe('name piece · “Haystack”');
  });
});

describe('StageBar', () => {
  it('renders one segment per stage with its state', () => {
    const segments = buildStageBar(
      [
        { label: 'ground', ops: 10 },
        { label: 'sky', ops: 100 },
        { label: 'water', ops: 50 },
      ],
      1
    );
    const { container } = render(<StageBar segments={segments} />);
    const segs = container.querySelectorAll('.stage-seg');
    expect(segs).toHaveLength(3);
    expect(segs[0]!.className).toContain('is-done');
    expect(segs[1]!.className).toContain('is-current');
    expect(segs[2]!.className).toContain('is-pending');
  });
});
