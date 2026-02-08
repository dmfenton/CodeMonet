/**
 * Tests for LiveStatus / useLiveStatus shared logic.
 *
 * Tests the status label derivation and visibility logic.
 * getStatusLabel now lives in shared useLiveStatus hook.
 */

import { getStatusLabel } from '@code-monet/shared';
import type { AgentStatus } from '@code-monet/shared';

describe('LiveStatus', () => {
  describe('getStatusLabel', () => {
    it('returns empty string for idle status', () => {
      expect(getStatusLabel('idle')).toBe('');
    });

    it('returns "Thinking" for thinking status', () => {
      expect(getStatusLabel('thinking')).toBe('Thinking');
    });

    it('returns "Drawing" for drawing status', () => {
      expect(getStatusLabel('drawing')).toBe('Drawing');
    });

    it('returns "Running code" for executing status without tool', () => {
      expect(getStatusLabel('executing')).toBe('Running code');
      expect(getStatusLabel('executing', null)).toBe('Running code');
    });

    it('returns tool-specific label for executing status with tool', () => {
      expect(getStatusLabel('executing', 'draw_paths')).toBe('drawing paths');
      expect(getStatusLabel('executing', 'generate_svg')).toBe('generating SVG');
      expect(getStatusLabel('executing', 'view_canvas')).toBe('viewing canvas');
      expect(getStatusLabel('executing', 'mark_piece_done')).toBe('marking done');
    });

    it('returns "Paused" for paused status', () => {
      expect(getStatusLabel('paused')).toBe('Paused');
    });

    it('returns "Error" for error status', () => {
      expect(getStatusLabel('error')).toBe('Error');
    });
  });

  describe('visibility logic', () => {
    // Tests for when LiveStatus should be shown/hidden
    const shouldShow = (status: AgentStatus, hasLiveMessage: boolean): boolean => {
      return !(status === 'idle' && !hasLiveMessage);
    };

    it('hides when idle and no live message', () => {
      expect(shouldShow('idle', false)).toBe(false);
    });

    it('shows when idle but has live message', () => {
      expect(shouldShow('idle', true)).toBe(true);
    });

    it('shows when thinking', () => {
      expect(shouldShow('thinking', false)).toBe(true);
      expect(shouldShow('thinking', true)).toBe(true);
    });

    it('shows when drawing', () => {
      expect(shouldShow('drawing', false)).toBe(true);
    });

    it('shows when executing', () => {
      expect(shouldShow('executing', false)).toBe(true);
    });

    it('shows when paused', () => {
      expect(shouldShow('paused', false)).toBe(true);
    });

    it('shows when error', () => {
      expect(shouldShow('error', false)).toBe(true);
    });
  });
});
