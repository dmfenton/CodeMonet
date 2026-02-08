/**
 * LiveStatus - Always-visible display of current agent activity.
 *
 * Adapts its presentation to what's currently happening:
 * - Events: Tool-specific icon + action text as a single activity row
 * - Thinking: Streaming text with cursor (no header needed)
 * - Active with no content: Minimal pulsing status indicator
 * - Paused/Error: Simple icon + label
 */

import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { AgentStatus, PerformanceState, ToolName } from '@code-monet/shared';
import { TOOL_DISPLAY_NAMES } from '@code-monet/shared';
import { borderRadius, spacing, typography, useTheme } from '../theme';
import { TOOL_ICONS, getToolBorderColor } from './messages/types';
import { debugRender } from '../utils/debugLog';

interface LiveStatusProps {
  /** Performance state (used for revealedText display) */
  performance: PerformanceState;
  /** Current agent status */
  status: AgentStatus;
  /** Current tool being used (for more specific status) */
  currentTool?: ToolName | null;
}

function getStatusIcon(status: AgentStatus): keyof typeof Ionicons.glyphMap {
  switch (status) {
    case 'thinking':
      return 'bulb-outline';
    case 'drawing':
      return 'brush';
    case 'executing':
      return 'code-working';
    case 'paused':
      return 'pause';
    case 'error':
      return 'alert-circle';
    default:
      return 'ellipse-outline';
  }
}

function getStatusLabel(status: AgentStatus, currentTool?: ToolName | null): string {
  if (status === 'executing' && currentTool) {
    return TOOL_DISPLAY_NAMES[currentTool] ?? 'Running code';
  }

  switch (status) {
    case 'thinking':
      return 'Thinking';
    case 'drawing':
      return 'Drawing';
    case 'executing':
      return 'Running code';
    case 'paused':
      return 'Paused';
    case 'error':
      return 'Error';
    default:
      return '';
  }
}

/** Renders a word (bionic reading disabled - renders as plain text) */
function BionicWord({ word }: { word: string }): React.JSX.Element {
  return <Text>{word}</Text>;
}

export function LiveStatus({
  performance,
  status,
  currentTool,
}: LiveStatusProps): React.JSX.Element | null {
  const { colors, shadows } = useTheme();
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const prevDisplayedCountRef = useRef(0);

  // Get revealed text from performance state
  const revealedText = performance.revealedText;

  // Get event message, icon, and styling if an event is currently on stage
  const eventDisplay = useMemo(() => {
    if (performance.onStage?.type === 'event') {
      const message = performance.onStage.message;
      const toolName = message.metadata?.tool_name ?? 'unknown';
      const iconConfig = TOOL_ICONS[toolName];
      const toolColor = getToolBorderColor(toolName, colors);
      const isInProgress =
        message.text.includes('...') &&
        !message.text.includes('Drew') &&
        !message.text.includes('generated');
      return {
        message,
        toolName,
        icon: isInProgress
          ? (iconConfig?.activeIcon ?? iconConfig?.name ?? 'ellipse-outline')
          : (iconConfig?.name ?? 'ellipse-outline'),
        toolColor,
        isInProgress,
      };
    }
    return null;
  }, [performance.onStage, colors]);

  // Split revealed text into words for bionic rendering
  const displayedWords = useMemo(
    () => revealedText.split(/\s+/).filter((w) => w.length > 0),
    [revealedText]
  );

  // Check if there are more words to reveal (buffer has words OR stage has words with more to reveal)
  const isBuffering = useMemo(() => {
    // Check if there are words items in the buffer
    const hasWordsInBuffer = performance.buffer.some((item) => item.type === 'words');
    // Check if current stage item is words and has more words to reveal
    if (performance.onStage?.type === 'words') {
      const totalWords = performance.onStage.text.split(/\s+/).filter((w) => w.length > 0).length;
      if (performance.wordIndex < totalWords) {
        return true;
      }
    }
    return hasWordsInBuffer;
  }, [performance.buffer, performance.onStage, performance.wordIndex]);

  const wordCount = displayedWords.length;

  // Log progressive text state changes
  if (displayedWords.length !== prevDisplayedCountRef.current) {
    debugRender(
      `LiveStatus: displayed=${displayedWords.length}/${wordCount} words, buffering=${isBuffering}`
    );
    prevDisplayedCountRef.current = displayedWords.length;
  }

  // Pulse animation for active states
  useEffect(() => {
    if (status === 'thinking' || status === 'drawing' || status === 'executing') {
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
  }, [status, pulseAnim]);

  // Don't show anything when idle and no content
  const hasContent = displayedWords.length > 0 || performance.buffer.length > 0 || !!eventDisplay;
  if (status === 'idle' && !hasContent) {
    return null;
  }

  const isActive = status === 'thinking' || status === 'drawing' || status === 'executing';

  // Event on stage → event becomes the entire display
  if (eventDisplay) {
    return (
      <View
        testID="live-status"
        style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
      >
        <View style={styles.activityRow}>
          <Animated.View style={eventDisplay.isInProgress ? { opacity: pulseAnim } : undefined}>
            <Ionicons
              name={eventDisplay.icon}
              size={18}
              color={eventDisplay.isInProgress ? eventDisplay.toolColor : colors.textMuted}
            />
          </Animated.View>
          <Text
            style={[
              styles.activityText,
              { color: eventDisplay.isInProgress ? colors.textPrimary : colors.textMuted },
            ]}
            numberOfLines={2}
          >
            {eventDisplay.message.text}
          </Text>
        </View>
      </View>
    );
  }

  // Thinking text → show text directly, no header
  if (displayedWords.length > 0) {
    return (
      <View
        testID="live-status"
        style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
      >
        <Text style={[styles.thoughtText, { color: colors.textPrimary }]} numberOfLines={3}>
          {displayedWords.map((word, i) => (
            <React.Fragment key={`${i}-${word}`}>
              <BionicWord word={word} />
              {i < displayedWords.length - 1 && ' '}
            </React.Fragment>
          ))}
          {isBuffering && <Text style={{ color: colors.textMuted }}> ▍</Text>}
        </Text>
      </View>
    );
  }

  // Active but no content yet → minimal pulsing indicator
  if (isActive) {
    const statusLabel = getStatusLabel(status, currentTool);
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
            {statusLabel}...
          </Text>
        </View>
      </View>
    );
  }

  // Paused/Error → simple indicator
  if (status !== 'idle') {
    const statusLabel = getStatusLabel(status);
    const statusIcon = getStatusIcon(status);
    const statusColor = status === 'error' ? colors.error : colors.textMuted;
    return (
      <View
        testID="live-status"
        style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
      >
        <View style={styles.activityRow}>
          <Ionicons name={statusIcon} size={16} color={statusColor} />
          <Text style={[styles.statusText, { color: statusColor }]}>
            {statusLabel}
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
