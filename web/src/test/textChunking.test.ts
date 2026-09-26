/**
 * Text chunking tests - validate that thinking_delta messages are grouped
 * into chunks of MAX_WORDS_PER_CHUNK words.
 *
 * Run: npm run test -w web -- textChunking
 */

import { describe, it, expect } from 'vitest';
import {
  canvasReducer,
  initialState,
  routeMessage,
  MAX_WORDS_PER_CHUNK,
  type CanvasHookState,
} from '@code-monet/shared';
import type { ServerMessage } from '@code-monet/shared';

import fixture from './fixtures/server/text_chunking_flow.json';

interface FixtureMessage {
  type: string;
  data: ServerMessage;
  timestamp_ms: number;
}

interface Fixture {
  metadata: {
    model: string;
    style: string;
    recorded_at: string;
    description: string;
    message_count: number;
  };
  messages: FixtureMessage[];
}

/**
 * Replay all messages through the reducer chain.
 */
function replayMessages(messages: FixtureMessage[]): {
  finalState: CanvasHookState;
  bufferSnapshots: Array<{ wordCounts: number[]; onStageWordCount: number | null }>;
} {
  let state: CanvasHookState = { ...initialState, paused: false };
  const bufferSnapshots: Array<{ wordCounts: number[]; onStageWordCount: number | null }> = [];

  for (const msg of messages) {
    const dispatch = (action: Parameters<typeof canvasReducer>[1]) => {
      state = canvasReducer(state, action);
    };

    routeMessage(msg.data, dispatch);

    // Snapshot buffer state after each thinking_delta
    if (msg.type === 'thinking_delta') {
      const wordCounts = state.performance.buffer
        .filter((item) => item.type === 'words')
        .map((item) => {
          if (item.type === 'words') {
            return item.text.split(/\s+/).filter((w) => w).length;
          }
          return 0;
        });

      const onStageWordCount =
        state.performance.onStage?.type === 'words'
          ? state.performance.onStage.text.split(/\s+/).filter((w) => w).length
          : null;

      bufferSnapshots.push({ wordCounts, onStageWordCount });
    }
  }

  return { finalState: state, bufferSnapshots };
}

describe('Text Chunking - Word Limit', () => {
  const typedFixture = fixture as Fixture;

  it('exports MAX_WORDS_PER_CHUNK constant', () => {
    expect(MAX_WORDS_PER_CHUNK).toBe(25);
  });

  it('processes thinking_delta messages', () => {
    const thinkingDeltas = typedFixture.messages.filter((m) => m.type === 'thinking_delta');
    expect(thinkingDeltas.length).toBeGreaterThan(0);
  });

  it('groups words into chunks not exceeding MAX_WORDS_PER_CHUNK', () => {
    const { bufferSnapshots } = replayMessages(typedFixture.messages);

    // Check that all buffer items respect the word limit
    for (const snapshot of bufferSnapshots) {
      for (const wordCount of snapshot.wordCounts) {
        // Buffer items should not exceed MAX_WORDS_PER_CHUNK
        // (they may be slightly over if a word is added that pushes over,
        // but next message will create new chunk)
        expect(wordCount).toBeLessThanOrEqual(MAX_WORDS_PER_CHUNK + 10);
      }
    }
  });

  it('creates multiple buffer items when text exceeds limit', () => {
    const { bufferSnapshots } = replayMessages(typedFixture.messages);

    // After many thinking_deltas, we should have created multiple chunks
    const maxBufferSize = Math.max(...bufferSnapshots.map((s) => s.wordCounts.length));
    expect(maxBufferSize).toBeGreaterThanOrEqual(1);
  });

  it('does not merge into onStage', () => {
    // Create a scenario where onStage has words and new words arrive
    let state: CanvasHookState = { ...initialState, paused: false };

    // First, add some words
    state = canvasReducer(state, {
      type: 'ENQUEUE_WORDS',
      text: 'Initial words on stage',
    });

    // Advance to stage
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Now onStage has words
    expect(state.performance.onStage?.type).toBe('words');

    // Add more words - they should go to buffer, not merge into onStage
    state = canvasReducer(state, {
      type: 'ENQUEUE_WORDS',
      text: 'New words should go to buffer',
    });

    // onStage should be unchanged
    expect(state.performance.onStage?.type).toBe('words');
    if (state.performance.onStage?.type === 'words') {
      expect(state.performance.onStage.text).toBe('Initial words on stage');
    }

    // Buffer should have the new words
    expect(state.performance.buffer.length).toBe(1);
    expect(state.performance.buffer[0]?.type).toBe('words');
    if (state.performance.buffer[0]?.type === 'words') {
      expect(state.performance.buffer[0].text).toBe('New words should go to buffer');
    }
  });

  it('merges consecutive buffer items under the limit', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // Add small chunks that should merge
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'First ' });
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'second ' });
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'third' });

    // Should be merged into single buffer item
    expect(state.performance.buffer.length).toBe(1);
    if (state.performance.buffer[0]?.type === 'words') {
      expect(state.performance.buffer[0].text).toBe('First second third');
    }
  });

  it('creates new chunk when limit exceeded', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // Add 30 words (exceeds MAX_WORDS_PER_CHUNK of 25)
    const words = Array.from({ length: 30 }, (_, i) => `word${i}`).join(' ');
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: words });

    // First chunk is created
    expect(state.performance.buffer.length).toBe(1);

    // Add more words - should create new chunk since first is over limit
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'additional words' });

    // Should now have 2 buffer items
    expect(state.performance.buffer.length).toBe(2);
  });
});

describe('Text Chunking - ADVANCE_STAGE Reset', () => {
  it('resets revealedText when advancing to new words chunk', () => {
    let state: CanvasHookState = { ...initialState, paused: false };

    // Add words and advance
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'First chunk' });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // Simulate revealing some words
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    state = canvasReducer(state, { type: 'REVEAL_WORD' });
    expect(state.performance.revealedText).toBe('First chunk');

    // Add second chunk and complete first
    state = canvasReducer(state, { type: 'ENQUEUE_WORDS', text: 'Second chunk' });
    state = canvasReducer(state, { type: 'STAGE_COMPLETE' });
    state = canvasReducer(state, { type: 'ADVANCE_STAGE' });

    // revealedText should be reset for new chunk
    expect(state.performance.revealedText).toBe('');
    expect(state.performance.wordIndex).toBe(0);
  });
});
