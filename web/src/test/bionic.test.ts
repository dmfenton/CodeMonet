/**
 * Tests for text utilities.
 */

import { describe, it, expect } from 'vitest';
import { chunkWords, getLastToolCall } from '@code-monet/shared';
import type { AgentMessage } from '@code-monet/shared';

describe('chunkWords', () => {
  it('splits text into chunks of specified size', () => {
    expect(chunkWords('one two three four', 2)).toEqual([
      ['one', 'two'],
      ['three', 'four'],
    ]);
  });

  it('handles trailing incomplete chunk', () => {
    expect(chunkWords('one two three', 2)).toEqual([['one', 'two'], ['three']]);
  });

  it('handles empty string', () => {
    expect(chunkWords('', 2)).toEqual([]);
  });

  it('handles whitespace-only string', () => {
    expect(chunkWords('   ', 2)).toEqual([]);
  });

  it('handles single word', () => {
    expect(chunkWords('hello', 2)).toEqual([['hello']]);
  });

  it('respects custom chunk size', () => {
    expect(chunkWords('a b c d e f', 3)).toEqual([
      ['a', 'b', 'c'],
      ['d', 'e', 'f'],
    ]);
  });

  it('handles multiple spaces between words', () => {
    expect(chunkWords('one   two    three', 2)).toEqual([['one', 'two'], ['three']]);
  });
});

describe('getLastToolCall', () => {
  it('returns null for empty messages', () => {
    expect(getLastToolCall([])).toBeNull();
  });

  it('returns null when no code_execution messages', () => {
    const messages: AgentMessage[] = [
      { id: '1', type: 'thinking', text: 'hello', timestamp: Date.now() },
    ];
    expect(getLastToolCall(messages)).toBeNull();
  });

  it('returns tool name from code_execution message', () => {
    const messages: AgentMessage[] = [
      {
        id: '1',
        type: 'code_execution',
        text: 'Drawing...',
        timestamp: Date.now(),
        metadata: { tool_name: 'draw_paths' },
      },
    ];
    expect(getLastToolCall(messages)).toBe('draw_paths');
  });

  it('returns most recent tool call', () => {
    const messages: AgentMessage[] = [
      {
        id: '1',
        type: 'code_execution',
        text: 'First',
        timestamp: Date.now(),
        metadata: { tool_name: 'view_canvas' },
      },
      { id: '2', type: 'thinking', text: 'thinking...', timestamp: Date.now() },
      {
        id: '3',
        type: 'code_execution',
        text: 'Second',
        timestamp: Date.now(),
        metadata: { tool_name: 'draw_paths' },
      },
    ];
    expect(getLastToolCall(messages)).toBe('draw_paths');
  });

  it('skips code_execution without tool_name', () => {
    const messages: AgentMessage[] = [
      {
        id: '1',
        type: 'code_execution',
        text: 'Has tool',
        timestamp: Date.now(),
        metadata: { tool_name: 'view_canvas' },
      },
      {
        id: '2',
        type: 'code_execution',
        text: 'No tool',
        timestamp: Date.now(),
        metadata: {},
      },
    ];
    expect(getLastToolCall(messages)).toBe('view_canvas');
  });
});
