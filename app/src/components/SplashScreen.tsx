/**
 * Code Monet Splash Screen
 * A bold, immersive splash with gradient orbs and dynamic animations,
 * matching the web homepage aesthetic.
 */

import React from 'react';
import { Animated, Dimensions, StyleSheet, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { spacing, typography, useTheme } from '../theme';
import { BrushStroke, GradientOrb, PaintSplatter, useSplashAnimation } from './splash';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

interface SplashScreenProps {
  onFinish: () => void;
}

export function SplashScreen({ onFinish }: SplashScreenProps): React.JSX.Element {
  const { colors, shadows } = useTheme();
  const anim = useSplashAnimation(onFinish);

  return (
    <Animated.View
      style={[styles.container, { backgroundColor: colors.background, opacity: anim.fadeOut }]}
    >
      {/* Gradient orbs background */}
      <Animated.View
        style={[
          styles.orbContainer,
          {
            opacity: anim.fadeIn,
            transform: [{ translateY: anim.orb1Transform }],
          },
        ]}
      >
        <Svg width={SCREEN_WIDTH} height={SCREEN_HEIGHT} style={styles.svg}>
          {/* Large gradient orbs */}
          <GradientOrb
            cx={SCREEN_WIDTH * 0.2}
            cy={SCREEN_HEIGHT * 0.2}
            size={SCREEN_WIDTH * 0.6}
            color1={colors.primary}
            color2={colors.secondary}
            gradientId="orb1"
          />
          <GradientOrb
            cx={SCREEN_WIDTH * 0.85}
            cy={SCREEN_HEIGHT * 0.35}
            size={SCREEN_WIDTH * 0.5}
            color1={colors.secondary}
            color2={colors.accent}
            gradientId="orb2"
          />
          <GradientOrb
            cx={SCREEN_WIDTH * 0.3}
            cy={SCREEN_HEIGHT * 0.75}
            size={SCREEN_WIDTH * 0.45}
            color1={colors.accent}
            color2={colors.primary}
            gradientId="orb3"
          />

          {/* Paint splatters */}
          <PaintSplatter x={SCREEN_WIDTH * 0.1} y={SCREEN_HEIGHT * 0.15} size={30} color={colors.primary} />
          <PaintSplatter x={SCREEN_WIDTH * 0.85} y={SCREEN_HEIGHT * 0.1} size={25} color={colors.accent} />
          <PaintSplatter x={SCREEN_WIDTH * 0.7} y={SCREEN_HEIGHT * 0.8} size={35} color={colors.secondary} />
          <PaintSplatter x={SCREEN_WIDTH * 0.15} y={SCREEN_HEIGHT * 0.85} size={20} color={colors.gold} />

          {/* Brush strokes */}
          <BrushStroke x={30} y={SCREEN_HEIGHT * 0.25} width={100} color={colors.primary} rotation={-8} />
          <BrushStroke x={SCREEN_WIDTH - 130} y={SCREEN_HEIGHT * 0.18} width={90} color={colors.secondary} rotation={5} />
          <BrushStroke x={50} y={SCREEN_HEIGHT * 0.78} width={80} color={colors.accent} rotation={-3} />
          <BrushStroke x={SCREEN_WIDTH - 110} y={SCREEN_HEIGHT * 0.82} width={70} color={colors.coral} rotation={6} />
        </Svg>
      </Animated.View>

      {/* Second floating layer */}
      <Animated.View
        style={[
          styles.orbContainer,
          {
            opacity: anim.fadeIn,
            transform: [{ translateY: anim.orb2Transform }],
          },
        ]}
      >
        <Svg width={SCREEN_WIDTH} height={SCREEN_HEIGHT} style={styles.svg}>
          <GradientOrb
            cx={SCREEN_WIDTH * 0.7}
            cy={SCREEN_HEIGHT * 0.6}
            size={SCREEN_WIDTH * 0.4}
            color1={colors.lavender}
            color2={colors.primary}
            gradientId="orb4"
          />
        </Svg>
      </Animated.View>

      {/* Title content */}
      <View style={styles.content}>
        <Animated.View
          style={[
            styles.titleContainer,
            {
              opacity: anim.fadeIn,
              transform: [{ translateY: anim.titleSlide }, { scale: anim.titleScale }],
            },
          ]}
        >
          <View style={styles.titleRow}>
            <Animated.Text style={[styles.titleCode, { color: colors.primary }]}>Code</Animated.Text>
            <Animated.Text style={[styles.titleMonet, { color: colors.textPrimary }]}>Monet</Animated.Text>
          </View>
          <View style={styles.titleUnderlineContainer}>
            <View style={[styles.titleUnderline, { backgroundColor: colors.primary }]} />
            <View style={[styles.titleUnderline, styles.titleUnderlineAccent, { backgroundColor: colors.accent }]} />
          </View>
        </Animated.View>

        <Animated.Text style={[styles.subtitle, { color: colors.textSecondary, opacity: anim.subtitleFade }]}>
          An autonomous AI artist
        </Animated.Text>

        <Animated.View style={[styles.iconContainer, { opacity: anim.subtitleFade }]}>
          <View style={[styles.brushIcon, shadows.glow]}>
            <Svg width={44} height={44} viewBox="0 0 44 44">
              <Defs>
                <LinearGradient id="brushGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <Stop offset="0%" stopColor={colors.primary} />
                  <Stop offset="100%" stopColor={colors.coral} />
                </LinearGradient>
              </Defs>
              <Path
                d="M10 34 Q14 30 18 26 L30 14 Q34 10 36 8 Q38 10 36 14 L24 26 Q20 30 16 34 Q12 38 10 34Z"
                fill="url(#brushGradient)"
              />
              <Circle cx={12} cy={34} r={4} fill={colors.accent} />
            </Svg>
          </View>
        </Animated.View>
      </View>

      {/* Bottom attribution */}
      <Animated.Text style={[styles.attribution, { color: colors.textMuted, opacity: anim.subtitleFade }]}>
        Powered by Claude
      </Animated.Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    inset: 0,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 100,
  },
  orbContainer: {
    position: 'absolute',
    inset: 0,
  },
  svg: {
    position: 'absolute',
  },
  content: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing['2xl'],
  },
  titleContainer: {
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.sm,
  },
  titleCode: {
    ...typography.artistic,
    fontWeight: '300',
  },
  titleMonet: {
    ...typography.artistic,
    fontWeight: '200',
  },
  titleUnderlineContainer: {
    flexDirection: 'row',
    marginTop: spacing.md,
    gap: spacing.xs,
  },
  titleUnderline: {
    width: 60,
    height: 3,
    borderRadius: 2,
  },
  titleUnderlineAccent: {
    width: 40,
  },
  subtitle: {
    ...typography.heading,
    textAlign: 'center',
    marginTop: spacing.sm,
    fontWeight: '400',
    letterSpacing: 1,
  },
  iconContainer: {
    marginTop: spacing['2xl'],
  },
  brushIcon: {
    padding: spacing.sm,
    borderRadius: 22,
  },
  attribution: {
    position: 'absolute',
    bottom: spacing['3xl'],
    ...typography.caption,
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
});
