/**
 * Notebook and stage bar rendering.
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { NotebookEntry } from '@code-monet/shared';
import { buildStageBar } from '@code-monet/shared';
import { Notebook } from '../components/studio/Notebook';
import { StageBar } from '../components/studio/StageBar';

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver;
});

const tool = (
  id: string,
  name: string,
  extra: Partial<Extract<NotebookEntry, { kind: 'tool' }>> = {}
): NotebookEntry => ({
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

const entries: NotebookEntry[] = [
  { kind: 'nudge', id: 'a', text: 'poplars at dusk', version: 1, prompt: true },
  { kind: 'thought', id: 'b', text: 'The sky carries it.', version: 1, open: false },
  tool('h1', 'Write'),
  tool('h2', 'Edit'),
  tool('h3', 'Write'),
  tool('h4', 'Bash'),
  tool('c', 'paint', { produced: { version: 1, ops: 3978 }, seconds: 13 }),
  {
    kind: 'critique',
    id: 'd',
    iteration: 1,
    verdict: 'fail',
    text: '- Reflections are **too literal**.\n- Soften the *water*.',
    version: 1,
  },
  { kind: 'thought', id: 'e', text: 'Softening the water.', version: 2, open: true },
];

describe('Notebook', () => {
  it('renders grouped housekeeping, domain labels, critique markdown, and the test id', () => {
    const { container } = render(
      <Notebook entries={entries} phase="thinking" latestVersion={1} canSend onNudge={() => {}} />
    );
    expect(screen.getByTestId('thinking-strip')).toBeTruthy();
    expect(screen.getByText('notebook · v1')).toBeTruthy();
    expect(screen.getByText('you · prompt')).toBeTruthy();
    // Four housekeeping calls collapse to one quiet line
    const housekeeping = container.querySelectorAll('.nb-housekeeping');
    expect(housekeeping).toHaveLength(1);
    expect(housekeeping[0]!.textContent).toBe('› write · edit · bash');
    expect(screen.getByText(/paint v1 · 3,978 strokes · 13\.0s/)).toBeTruthy();
    expect(screen.getByText('critique · fail')).toBeTruthy();
    // Markdown, not raw asterisks
    expect(container.querySelector('.nb-critique strong')?.textContent).toBe('too literal');
    expect(container.querySelector('.nb-critique em')?.textContent).toBe('water');
    expect(container.querySelectorAll('.nb-critique li')).toHaveLength(2);
    expect(container.textContent).not.toContain('**');
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
});

describe('StageBar', () => {
  const segments = buildStageBar(
    [
      { label: 'ground', ops: 10 },
      { label: 'sky', ops: 100 },
      { label: 'water', ops: 50 },
    ],
    1
  );

  it('renders one segment per stage with its state and a hover title', () => {
    const { container } = render(<StageBar segments={segments} />);
    const segs = container.querySelectorAll('.stage-seg');
    expect(segs).toHaveLength(3);
    expect(segs[0]!.className).toContain('is-done');
    expect(segs[1]!.className).toContain('is-current');
    expect(segs[2]!.className).toContain('is-pending');
    expect(segs[1]!.getAttribute('title')).toContain('sky');
  });

  it('falls back to one caption when labels cannot be measured to fit', () => {
    // jsdom has no layout: width 0, so per-segment labels are hidden
    render(<StageBar segments={segments} />);
    expect(screen.getByTestId('stage-caption').textContent).toBe('stage 2 of 3 · sky');
  });
});
