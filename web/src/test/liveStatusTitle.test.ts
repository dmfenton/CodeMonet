/**
 * Server-driven turn state and piece titles:
 * init.turn_active / turn_state -> turnActive -> status; piece_title -> title.
 */

import { describe, expect, it } from 'vitest';
import type { CanvasAction, CanvasHookState, InitMessage, ServerMessage } from '@code-monet/shared';
import {
  canvasReducer,
  deriveAgentStatus,
  deriveStudioPhase,
  initialState,
  routeMessage,
} from '@code-monet/shared';

const play = (state: CanvasHookState, ...messages: ServerMessage[]): CanvasHookState => {
  let s = state;
  for (const message of messages) {
    routeMessage(message, (action: CanvasAction) => {
      s = canvasReducer(s, action);
    });
  }
  return s;
};

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

const turn = (active: boolean): ServerMessage => ({ type: 'turn_state', active });

describe('turn state', () => {
  it('reads init.turn_active', () => {
    const s = play(initialState, init({ turn_active: true }));
    expect(s.turnActive).toBe(true);
    expect(deriveAgentStatus(s)).toBe('thinking');
  });

  it('treats an absent init.turn_active as no turn (older servers)', () => {
    const s = play(play(initialState, turn(true)), init());
    expect(s.turnActive).toBe(false);
    expect(deriveAgentStatus(s)).toBe('idle');
  });

  it('follows turn_state start and end', () => {
    const started = play(play(initialState, init()), turn(true));
    expect(started.turnActive).toBe(true);
    expect(deriveAgentStatus(started)).toBe('thinking');
    expect(deriveStudioPhase(deriveAgentStatus(started), null)).toBe('thinking');
    const ended = play(started, turn(false));
    expect(ended.turnActive).toBe(false);
    expect(deriveAgentStatus(ended)).toBe('idle');
  });

  it('never overrides paused or error', () => {
    const active = play(play(initialState, init({ turn_active: true })), turn(true));
    expect(deriveAgentStatus(play(active, { type: 'paused', paused: true }))).toBe('paused');
    expect(deriveAgentStatus(play(active, { type: 'error', message: 'boom' }))).toBe('error');
  });

  it('keeps higher-priority activity statuses', () => {
    const active = play(play(initialState, init({ turn_active: true })), {
      type: 'code_execution',
      status: 'started',
      tool_name: 'paint',
      iteration: 1,
    });
    expect(deriveAgentStatus(active)).toBe('executing');
  });
});

describe('piece_title', () => {
  const title = (piece_number: number, t: string): ServerMessage => ({
    type: 'piece_title',
    piece_number,
    title: t,
  });

  it('sets the title for the current piece', () => {
    const s = play(play(initialState, init()), title(4, '  Still Water, Dusk '));
    expect(s.pieceTitle).toBe('Still Water, Dusk');
  });

  it('ignores titles for other pieces', () => {
    const s = play(play(initialState, init({ title: 'Kept' })), title(3, 'Old piece'));
    expect(s.pieceTitle).toBe('Kept');
  });

  it('init.title still seeds the title on connect', () => {
    expect(play(initialState, init({ title: 'From init' })).pieceTitle).toBe('From init');
  });
});
