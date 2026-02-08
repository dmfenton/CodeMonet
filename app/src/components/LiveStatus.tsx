/**
 * LiveStatus - Always-visible display of current agent activity.
 *
 * Adapts its presentation to what's currently happening:
 * - Events: Tool-specific icon + action text as a single activity row
 * - Thinking: Streaming text with cursor (no header needed)
 * - Active with no content: Minimal pulsing status indicator
 * - Paused/Error: Simple icon + label
 *
 * Display logic lives in shared useLiveStatus hook -
 * this component is a thin React Native renderer.
 */

import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { AgentStatus, PerformanceState, ToolName } from '@code-monet/shared';
import { useLiveStatus } from '@code-monet/shared';
import { borderRadius, spacing, typography, useTheme } from '../theme';
import { TOOL_ICONS, getToolBorderColor } from './messages/types';

interface LiveStatusProps {
  /** Performance state (used for revealedText display) */
  performance: PerformanceState;
  /** Current agent status */
  status: AgentStatus;
  /** Current tool being used (for more specific status) */
  currentTool?: ToolName | null;
}

function getStatusIcon(status: 'paused' | 'error'): keyof typeof Ionicons.glyphMap {
  return status === 'error' ? 'alert-circle' : 'pause';
}

export function LiveStatus({
  performance,
  status,
  currentTool,
}: LiveStatusProps): React.JSX.Element | null {
  const { colors, shadows } = useTheme();
  const pulseAnim = useRef(new Animated.Value(1)).current;

  const display = useLiveStatus(performance, status, currentTool);

  // Pulse animation for active states
  const isActive = status === 'thinking' || status === 'drawing' || status === 'executing';
  useEffect(() => {
    if (isActive) {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 0.4,
            duration: 800,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 800,
            useNativeDriver: true,
          }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    } else {
      pulseAnim.setValue(1);
    }
  }, [isActive, pulseAnim]);

  if (display.type === 'hidden') {
    return null;
  }

  // Event on stage -> tool icon + action text
  if (display.type === 'event') {
    const iconConfig = TOOL_ICONS[display.toolName] ?? TOOL_ICONS.unknown;
    const toolColor = getToolBorderColor(display.toolName, colors);
    const icon = display.isInProgress
      ? (iconConfig.activeIcon ?? iconConfig.name)
      : iconConfig.name;

    return (
      <View
        testID="live-status"
        style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
      >
        <View style={styles.activityRow}>
          <Animated.View style={display.isInProgress ? { opacity: pulseAnim } : undefined}>
            <Ionicons
              name={icon}
              size={18}
              color={display.isInProgress ? toolColor : colors.textMuted}
            />
          </Animated.View>
          <Text
            style={[
              styles.activityText,
              { color: display.isInProgress ? colors.textPrimary : colors.textMuted },
            ]}
            numberOfLines={2}
          >
            {display.text}
          </Text>
        </View>
      </View>
    );
  }

  // Thinking text -> show text directly, no header
  if (display.type === 'thinking') {
    return (
      <View
        testID="live-status"
        style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
      >
        <Text style={[styles.thoughtText, { color: colors.textPrimary }]} numberOfLines={3}>
          {display.words.map((word, i) => (
            <React.Fragment key={`${i}-${word}`}>
              <Text>{word}</Text>
              {i < display.words.length - 1 && ' '}
            </React.Fragment>
          ))}
          {display.isBuffering && <Text style={{ color: colors.textMuted }}> ▍</Text>}
        </Text>
      </View>
    );
  }

  // Active but no content yet -> pulsing dot + label
  if (display.type === 'active') {
    return (
      <View
        testID="live-status"
        style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
      >
        <View style={styles.activityRow}>
          <Animated.View style={{ opacity: pulseAnim }}>
            <View style={[styles.activityDot, { backgroundColor: colors.primary }]} />
          </Animated.View>
          <Text style={[styles.statusText, { color: colors.primary }]}>
            {display.label}...
          </Text>
        </View>
      </View>
    );
  }

  // Paused / Error -> icon + label
  if (display.type === 'inactive') {
    const statusColor = display.statusType === 'error' ? colors.error : colors.textMuted;
    return (
      <View
        testID="live-status"
        style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
      >
        <View style={styles.activityRow}>
          <Ionicons name={getStatusIcon(display.statusType)} size={16} color={statusColor} />
          <Text style={[styles.statusText, { color: statusColor }]}>
            {display.label}
          </Text>
        </View>
      </View>
    );
  }

  return null;
}

const styles = StyleSheet.create({
  container: {
    borderRadius: borderRadius.md,
    padding: spacing.md,
  },
  activityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  activityDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  activityText: {
    ...typography.caption,
    fontWeight: '500',
    flex: 1,
  },
  statusText: {
    ...typography.small,
    fontWeight: '600',
  },
  thoughtText: {
    ...typography.body,
    lineHeight: 22,
  },
});
