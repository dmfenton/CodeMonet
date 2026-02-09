/**
 * LiveStatus - Always-visible display of current agent activity.
 *
 * Shows:
 * - Streaming thoughts as they arrive (from performance.revealedText)
 * - Current action: Drawing, Executing, etc.
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
      const borderColor = getToolBorderColor(toolName, colors);
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
        borderColor,
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
            toValue: 0.6,
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

  // When an event is on stage, override the header with tool-specific info
  const displayIcon = eventDisplay
    ? eventDisplay.icon
    : getStatusIcon(status);
  const displayLabel = eventDisplay
    ? (TOOL_DISPLAY_NAMES[eventDisplay.toolName as ToolName] ?? getStatusLabel(status, currentTool))
    : getStatusLabel(status, currentTool);
  const displayColor = eventDisplay
    ? eventDisplay.borderColor
    : (isActive ? colors.primary : colors.textMuted);

  return (
    <View
      testID="live-status"
      style={[styles.container, { backgroundColor: colors.surface }, shadows.sm]}
    >
      {/* Status indicator */}
      <View style={styles.statusRow}>
        <Animated.View style={{ opacity: pulseAnim }}>
          <Ionicons
            name={displayIcon}
            size={16}
            color={displayColor}
          />
        </Animated.View>
        <Text style={[styles.statusText, { color: displayColor }]}>
          {displayLabel}
          {isActive && '...'}
        </Text>
      </View>

      {/* Event replaces thinking text permanently - displayed like message bubbles */}
      {eventDisplay ? (
        <View
          style={[
            styles.eventBubble,
            {
              backgroundColor: colors.surfaceElevated,
              borderLeftColor: eventDisplay.borderColor,
            },
          ]}
        >
          <View style={styles.eventHeader}>
            <Ionicons name={eventDisplay.icon} size={16} color={eventDisplay.borderColor} />
            <Text style={[styles.eventText, { color: colors.textPrimary }]} numberOfLines={2}>
              {eventDisplay.message.text}
            </Text>
          </View>
        </View>
      ) : displayedWords.length > 0 ? (
        <Text style={[styles.thoughtText, { color: colors.textPrimary }]} numberOfLines={3}>
          {displayedWords.map((word, i) => (
            <React.Fragment key={`${i}-${word}`}>
              <BionicWord word={word} />
              {i < displayedWords.length - 1 && ' '}
            </React.Fragment>
          ))}
          {isBuffering && <Text style={{ color: colors.textMuted }}> ▍</Text>}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: borderRadius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  statusText: {
    ...typography.small,
    fontWeight: '600',
  },
  thoughtText: {
    ...typography.body,
    lineHeight: 22,
  },
  eventBubble: {
    borderRadius: borderRadius.sm,
    borderLeftWidth: 3,
    padding: spacing.sm,
  },
  eventHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  eventText: {
    ...typography.body,
    flex: 1,
  },
});
