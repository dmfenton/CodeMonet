/**
 * Floating particles animation for idle canvas state (web version).
 * Shows gentle, drifting particles when there's nothing on the canvas.
 */

import React, { useMemo } from 'react';
import { CANVAS_HEIGHT, CANVAS_WIDTH } from '@code-monet/shared';

// Particle colors - Fenton palette (forest, moss, terracotta, brass)
const PARTICLE_COLORS = [
  'rgba(31, 77, 52, 0.22)', // Forest
  'rgba(58, 122, 83, 0.24)', // Moss
  'rgba(184, 90, 46, 0.2)', // Terracotta
  'rgba(196, 181, 142, 0.35)', // Brass paper
  'rgba(148, 184, 158, 0.3)', // Lily vein
];

const PARTICLE_COUNT = 12;

interface Particle {
  id: number;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  radius: number;
  color: string;
  duration: number;
  delay: number;
}

function generateParticles(): Particle[] {
  const particles: Particle[] = [];
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    // Start from random positions
    const startX = Math.random() * CANVAS_WIDTH;
    const startY = Math.random() * CANVAS_HEIGHT;

    // Drift in a random direction
    const angle = Math.random() * Math.PI * 2;
    const distance = 100 + Math.random() * 200;

    particles.push({
      id: i,
      startX,
      startY,
      endX: startX + Math.cos(angle) * distance,
      endY: startY + Math.sin(angle) * distance,
      radius: 4 + Math.random() * 12, // 4-16 radius
      color: PARTICLE_COLORS[i % PARTICLE_COLORS.length]!,
      duration: 12 + Math.random() * 8, // 12-20 seconds
      delay: Math.random() * 5, // 0-5 second delay
    });
  }
  return particles;
}

interface IdleParticlesProps {
  visible: boolean;
}

export function IdleParticles({ visible }: IdleParticlesProps): React.ReactElement | null {
  // Generate particles once on mount
  const particles = useMemo(() => generateParticles(), []);

  if (!visible) return null;

  return (
    <g className="idle-particles">
      {/* Define unique animations for each particle */}
      <defs>
        <style>
          {particles
            .map(
              (p) => `
            @keyframes float-${p.id} {
              0%, 100% {
                transform: translate(${p.startX}px, ${p.startY}px);
              }
              50% {
                transform: translate(${p.endX}px, ${p.endY}px);
              }
            }
          `
            )
            .join('\n')}
        </style>
      </defs>

      {particles.map((particle) => (
        <circle
          key={particle.id}
          r={particle.radius}
          fill={particle.color}
          style={{
            animation: `float-${particle.id} ${particle.duration}s ease-in-out infinite`,
            animationDelay: `${particle.delay}s`,
            opacity: 0,
            animationFillMode: 'both',
          }}
        >
          {/* Fade in animation */}
          <animate
            attributeName="opacity"
            from="0"
            to="1"
            dur="1s"
            begin={`${particle.delay}s`}
            fill="freeze"
          />
        </circle>
      ))}
    </g>
  );
}
