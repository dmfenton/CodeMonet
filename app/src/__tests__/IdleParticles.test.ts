/**
 * Tests for IdleParticles component logic.
 *
 * Tests the particle generation and animation logic.
 * Note: We test the logic inline since we can't import React Native components.
 */

import { CANVAS_HEIGHT, CANVAS_WIDTH } from '@code-monet/shared';

// Particle colors - soft, artistic palette (same as component)
const PARTICLE_COLORS = [
  'rgba(123, 104, 238, 0.3)', // Lavender
  'rgba(78, 205, 196, 0.3)', // Teal
  'rgba(255, 107, 107, 0.25)', // Coral
  'rgba(255, 217, 61, 0.2)', // Gold
  'rgba(233, 69, 96, 0.25)', // Rose
];

const PARTICLE_COUNT = 12;
const ANIMATION_DURATION = 15000;

interface Particle {
  id: number;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  radius: number;
  color: string;
  delay: number;
}

/**
 * Generate particles for idle animation.
 * This mirrors the implementation in SkiaIdleParticles.tsx.
 */
function generateParticles(): Particle[] {
  const particles: Particle[] = [];
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const startX = Math.random() * CANVAS_WIDTH;
    const startY = Math.random() * CANVAS_HEIGHT;

    const angle = Math.random() * Math.PI * 2;
    const distance = 100 + Math.random() * 200;

    particles.push({
      id: i,
      startX,
      startY,
      endX: startX + Math.cos(angle) * distance,
      endY: startY + Math.sin(angle) * distance,
      radius: 4 + Math.random() * 12,
      color: PARTICLE_COLORS[i % PARTICLE_COLORS.length]!,
      delay: Math.random() * ANIMATION_DURATION * 0.5,
    });
  }
  return particles;
}

describe('IdleParticles', () => {
  describe('generateParticles', () => {
    it('generates the correct number of particles', () => {
      const particles = generateParticles();
      expect(particles).toHaveLength(PARTICLE_COUNT);
    });

    it('assigns unique ids to each particle', () => {
      const particles = generateParticles();
      const ids = particles.map((p) => p.id);
      const uniqueIds = new Set(ids);
      expect(uniqueIds.size).toBe(PARTICLE_COUNT);
    });

    it('generates start positions within canvas bounds', () => {
      const particles = generateParticles();
      particles.forEach((particle) => {
        expect(particle.startX).toBeGreaterThanOrEqual(0);
        expect(particle.startX).toBeLessThanOrEqual(CANVAS_WIDTH);
        expect(particle.startY).toBeGreaterThanOrEqual(0);
        expect(particle.startY).toBeLessThanOrEqual(CANVAS_HEIGHT);
      });
    });

    it('generates radius within expected range (4-16)', () => {
      const particles = generateParticles();
      particles.forEach((particle) => {
        expect(particle.radius).toBeGreaterThanOrEqual(4);
        expect(particle.radius).toBeLessThanOrEqual(16);
      });
    });

    it('assigns colors from the palette', () => {
      const particles = generateParticles();
      particles.forEach((particle) => {
        expect(PARTICLE_COLORS).toContain(particle.color);
      });
    });

    it('generates delays within expected range', () => {
      const particles = generateParticles();
      const maxDelay = ANIMATION_DURATION * 0.5;
      particles.forEach((particle) => {
        expect(particle.delay).toBeGreaterThanOrEqual(0);
        expect(particle.delay).toBeLessThanOrEqual(maxDelay);
      });
    });

    it('generates drift distance within expected range (100-300)', () => {
      const particles = generateParticles();
      particles.forEach((particle) => {
        const dx = particle.endX - particle.startX;
        const dy = particle.endY - particle.startY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        expect(distance).toBeGreaterThanOrEqual(100);
        expect(distance).toBeLessThanOrEqual(300);
      });
    });
  });

  describe('visibility logic', () => {
    /**
     * Determine if particles should be visible.
     * Particles show when canvas is completely empty.
     */
    function shouldShowParticles(
      strokeCount: number,
      currentStrokeLength: number,
      agentStrokeLength: number
    ): boolean {
      return strokeCount === 0 && currentStrokeLength === 0 && agentStrokeLength === 0;
    }

    it('shows particles when canvas is completely empty', () => {
      expect(shouldShowParticles(0, 0, 0)).toBe(true);
    });

    it('hides particles when there are completed strokes', () => {
      expect(shouldShowParticles(1, 0, 0)).toBe(false);
      expect(shouldShowParticles(5, 0, 0)).toBe(false);
    });

    it('hides particles when user is drawing', () => {
      expect(shouldShowParticles(0, 1, 0)).toBe(false);
      expect(shouldShowParticles(0, 10, 0)).toBe(false);
    });

    it('hides particles when agent is drawing', () => {
      expect(shouldShowParticles(0, 0, 1)).toBe(false);
      expect(shouldShowParticles(0, 0, 50)).toBe(false);
    });

    it('hides particles when any combination of strokes exist', () => {
      expect(shouldShowParticles(1, 1, 1)).toBe(false);
      expect(shouldShowParticles(5, 0, 10)).toBe(false);
      expect(shouldShowParticles(0, 5, 10)).toBe(false);
    });
  });
});
