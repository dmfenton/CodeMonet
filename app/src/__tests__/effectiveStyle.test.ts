/**
 * Tests for getEffectiveStyle and getEffectiveAgentStrokeStyle helpers.
 *
 * These functions compute the effective stroke style by merging path-level
 * overrides with style configuration defaults, respecting mode flags.
 */

import {
  getEffectiveStyle,
  getEffectiveAgentStrokeStyle,
  PLOTTER_STYLE,
  PAINT_STYLE,
} from '@code-monet/shared';
import type { Path } from '@code-monet/shared';

describe('getEffectiveAgentStrokeStyle', () => {
  describe('with null/undefined agentStrokeStyle', () => {
    it('returns agent_stroke defaults when agentStrokeStyle is null', () => {
      const style = getEffectiveAgentStrokeStyle(PLOTTER_STYLE, null);

      expect(style).toEqual(PLOTTER_STYLE.agent_stroke);
    });

    it('returns agent_stroke defaults when agentStrokeStyle is undefined', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, undefined);

      expect(style).toEqual(PAINT_STYLE.agent_stroke);
    });
  });

  describe('in plotter mode (supports_* flags are false)', () => {
    it('ignores color override', () => {
      const style = getEffectiveAgentStrokeStyle(PLOTTER_STYLE, { color: '#ff0000' });

      expect(style.color).toBe(PLOTTER_STYLE.agent_stroke.color);
    });

    it('ignores stroke_width override', () => {
      const style = getEffectiveAgentStrokeStyle(PLOTTER_STYLE, { stroke_width: 20 });

      expect(style.stroke_width).toBe(PLOTTER_STYLE.agent_stroke.stroke_width);
    });

    it('ignores opacity override', () => {
      const style = getEffectiveAgentStrokeStyle(PLOTTER_STYLE, { opacity: 0.5 });

      expect(style.opacity).toBe(PLOTTER_STYLE.agent_stroke.opacity);
    });

    it('ignores all overrides together', () => {
      const style = getEffectiveAgentStrokeStyle(PLOTTER_STYLE, {
        color: '#ff0000',
        stroke_width: 20,
        opacity: 0.5,
      });

      expect(style).toEqual(PLOTTER_STYLE.agent_stroke);
    });
  });

  describe('in paint mode (supports_* flags are true)', () => {
    it('uses color override when provided', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { color: '#ff0000' });

      expect(style.color).toBe('#ff0000');
    });

    it('uses stroke_width override when provided', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { stroke_width: 20 });

      expect(style.stroke_width).toBe(20);
    });

    it('uses opacity override when provided', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { opacity: 0.5 });

      expect(style.opacity).toBe(0.5);
    });

    it('uses all overrides together', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, {
        color: '#ff0000',
        stroke_width: 20,
        opacity: 0.5,
      });

      expect(style.color).toBe('#ff0000');
      expect(style.stroke_width).toBe(20);
      expect(style.opacity).toBe(0.5);
    });

    it('falls back to defaults for missing overrides', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { color: '#ff0000' });

      expect(style.color).toBe('#ff0000');
      expect(style.stroke_width).toBe(PAINT_STYLE.agent_stroke.stroke_width);
      expect(style.opacity).toBe(PAINT_STYLE.agent_stroke.opacity);
    });
  });

  describe('edge cases', () => {
    it('allows opacity of 0 (fully transparent)', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { opacity: 0 });

      expect(style.opacity).toBe(0);
    });

    it('does not use null as opacity override', () => {
      // This is critical: server sends null for unset fields, which should not override defaults
      // null !== undefined is true, so we must explicitly check for number type
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, {
        opacity: null as unknown as number,
      });

      expect(style.opacity).toBe(PAINT_STYLE.agent_stroke.opacity);
    });

    it('does not use empty string as color override', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { color: '' });

      expect(style.color).toBe(PAINT_STYLE.agent_stroke.color);
    });

    it('allows 0 as stroke_width override for fill-only shapes', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { stroke_width: 0 });

      expect(style.stroke_width).toBe(0);
    });
  });

  describe('always returns complete StrokeStyle', () => {
    it('includes stroke_linecap from agent_stroke', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { color: '#ff0000' });

      expect(style.stroke_linecap).toBe(PAINT_STYLE.agent_stroke.stroke_linecap);
    });

    it('includes stroke_linejoin from agent_stroke', () => {
      const style = getEffectiveAgentStrokeStyle(PAINT_STYLE, { color: '#ff0000' });

      expect(style.stroke_linejoin).toBe(PAINT_STYLE.agent_stroke.stroke_linejoin);
    });

    it('has all required StrokeStyle properties', () => {
      const style = getEffectiveAgentStrokeStyle(PLOTTER_STYLE, null);

      expect(style).toHaveProperty('color');
      expect(style).toHaveProperty('stroke_width');
      expect(style).toHaveProperty('opacity');
      expect(style).toHaveProperty('stroke_linecap');
      expect(style).toHaveProperty('stroke_linejoin');
    });
  });
});

describe('getEffectiveStyle', () => {
  // Helper to create test paths
  function makePath(overrides: Partial<Path> = {}): Path {
    return {
      type: 'polyline',
      points: [{ x: 0, y: 0 }],
      ...overrides,
    };
  }

  describe('author detection', () => {
    it('uses agent_stroke for agent author', () => {
      const path = makePath({ author: 'agent' });
      const style = getEffectiveStyle(path, PLOTTER_STYLE);

      expect(style.color).toBe(PLOTTER_STYLE.agent_stroke.color);
    });

    it('uses human_stroke for human author', () => {
      const path = makePath({ author: 'human' });
      const style = getEffectiveStyle(path, PLOTTER_STYLE);

      expect(style.color).toBe(PLOTTER_STYLE.human_stroke.color);
    });

    it('defaults to agent_stroke when author is not set', () => {
      const path = makePath();
      const style = getEffectiveStyle(path, PLOTTER_STYLE);

      expect(style.color).toBe(PLOTTER_STYLE.agent_stroke.color);
    });
  });

  describe('in plotter mode', () => {
    it('ignores path-level color override', () => {
      const path = makePath({ author: 'agent', color: '#ff0000' });
      const style = getEffectiveStyle(path, PLOTTER_STYLE);

      expect(style.color).toBe(PLOTTER_STYLE.agent_stroke.color);
    });

    it('returns exact default style', () => {
      const path = makePath({ author: 'agent', color: '#ff0000', stroke_width: 20 });
      const style = getEffectiveStyle(path, PLOTTER_STYLE);

      expect(style).toEqual(PLOTTER_STYLE.agent_stroke);
    });
  });

  describe('in paint mode', () => {
    it('uses path-level color when supports_color is true', () => {
      const path = makePath({ author: 'agent', color: '#ff0000' });
      const style = getEffectiveStyle(path, PAINT_STYLE);

      expect(style.color).toBe('#ff0000');
    });

    it('uses path-level stroke_width when supports_variable_width is true', () => {
      const path = makePath({ author: 'agent', stroke_width: 20 });
      const style = getEffectiveStyle(path, PAINT_STYLE);

      expect(style.stroke_width).toBe(20);
    });

    it('allows path-level stroke_width of 0 for fill-only shapes', () => {
      const path = makePath({ author: 'agent', stroke_width: 0 });
      const style = getEffectiveStyle(path, PAINT_STYLE);

      expect(style.stroke_width).toBe(0);
    });

    it('uses path-level opacity when supports_opacity is true', () => {
      const path = makePath({ author: 'agent', opacity: 0.5 });
      const style = getEffectiveStyle(path, PAINT_STYLE);

      expect(style.opacity).toBe(0.5);
    });

    it('allows opacity of 0', () => {
      const path = makePath({ author: 'agent', opacity: 0 });
      const style = getEffectiveStyle(path, PAINT_STYLE);

      expect(style.opacity).toBe(0);
    });

    it('does not use null as opacity override', () => {
      // Server sends null for unset fields, which should not override defaults
      const path = makePath({ author: 'agent', opacity: null as unknown as number });
      const style = getEffectiveStyle(path, PAINT_STYLE);

      expect(style.opacity).toBe(PAINT_STYLE.agent_stroke.opacity);
    });
  });
});
