/**
 * Floating particles animation for idle canvas state (Skia version).
 * Shows gentle, drifting particles when there's nothing on the canvas.
 *
 * Uses Skia Circle + Reanimated shared values for GPU-accelerated rendering
 * instead of Animated.createAnimatedComponent(Circle) from react-native-svg.
 */

import React, { useEffect, useMemo } from 'react';
import { Circle, Group } from '@shopify/react-native-skia';
import {
  useSharedValue,
  withTiming,
  withRepeat,
  withSequence,
  withDelay,
  Easing,
  useDerivedValue,
  cancelAnimation,
} from 'react-native-reanimated';
import { CANVAS_HEIGHT, CANVAS_WIDTH } from '@code-monet/shared';

// Particle colors - soft, artistic palette (Skia uses hex/rgba strings)
const PARTICLE_COLORS = [
  'rgba(123, 104, 238, 0.3)', // Lavender
  'rgba(78, 205, 196, 0.3)', // Teal
  'rgba(255, 107, 107, 0.25)', // Coral
  'rgba(255, 217, 61, 0.2)', // Gold
  'rgba(233, 69, 96, 0.25)', // Rose
];

const PARTICLE_COUNT = 12;
const ANIMATION_DURATION = 15000; // 15 seconds for a full cycle

interface ParticleData {
  id: number;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  radius: number;
  color: string;
  delay: number;
}

function generateParticles(): ParticleData[] {
  const particles: ParticleData[] = [];
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

/**
 * Single animated particle using Reanimated shared values.
 */
function AnimatedParticle({
  particle,
  visible,
}: {
  particle: ParticleData;
  visible: boolean;
}): React.ReactElement | null {
  const progress = useSharedValue(0);
  const opacity = useSharedValue(0);

  useEffect(() => {
    if (visible) {
      // Fade in
      opacity.value = withDelay(
        particle.delay,
        withTiming(1, { duration: 1000 })
      );

      // Movement loop: 0 -> 1 -> 0 with sine easing
      progress.value = withDelay(
        particle.delay,
        withRepeat(
          withSequence(
            withTiming(1, { duration: ANIMATION_DURATION, easing: Easing.inOut(Easing.sin) }),
            withTiming(0, { duration: ANIMATION_DURATION, easing: Easing.inOut(Easing.sin) })
          ),
          -1 // infinite
        )
      );
    } else {
      opacity.value = withTiming(0, { duration: 500 });
      cancelAnimation(progress);
      progress.value = 0;
    }

    return () => {
      cancelAnimation(progress);
      cancelAnimation(opacity);
    };
  }, [visible, particle.delay, progress, opacity]);

  const cx = useDerivedValue(() => {
    return particle.startX + (particle.endX - particle.startX) * progress.value;
  });

  const cy = useDerivedValue(() => {
    return particle.startY + (particle.endY - particle.startY) * progress.value;
  });

  return (
    <Circle
      cx={cx}
      cy={cy}
      r={particle.radius}
      color={particle.color}
      opacity={opacity}
    />
  );
}

interface SkiaIdleParticlesProps {
  visible: boolean;
}

export function SkiaIdleParticles({ visible }: SkiaIdleParticlesProps): React.ReactElement | null {
  const particles = useMemo(() => generateParticles(), []);

  if (!visible) return null;

  return (
    <Group>
      {particles.map((particle) => (
        <AnimatedParticle key={particle.id} particle={particle} visible={visible} />
      ))}
    </Group>
  );
}
