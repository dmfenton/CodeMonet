/**
 * HomePanel - Home screen shown on app load.
 * Prioritizes new drawing creation with prompt input and style picker.
 * Shows continue option with thumbnail when recent work exists.
 */

import React, { useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { DrawingStyleConfig, DrawingStyleType, Path, SavedCanvas } from '@code-monet/shared';
import type { ApiClient } from '../api';
import { useRendererConfig } from '../context/RendererContext';
import { spacing, borderRadius, typography, useTheme } from '../theme';
import { RendererPicker } from './RendererPicker';
import { StylePicker } from './StylePicker';
import { ContinueCard, PromptInput } from './home';

interface HomePanelProps {
  api: ApiClient;
  connected: boolean;
  hasCurrentWork: boolean;
  pieceNumber: number;
  recentCanvas: SavedCanvas | null;
  drawingStyle: DrawingStyleType;
  strokes: Path[];
  styleConfig: DrawingStyleConfig;
  galleryCount: number;
  onStyleChange: (style: DrawingStyleType) => void;
  onContinue: () => void;
  onStartWithPrompt: (prompt: string) => void;
  onSurpriseMe: () => void;
  onOpenGallery: () => void;
}

export function HomePanel({
  api,
  connected,
  hasCurrentWork,
  pieceNumber,
  recentCanvas,
  drawingStyle,
  strokes,
  styleConfig,
  galleryCount,
  onStyleChange,
  onContinue,
  onStartWithPrompt,
  onSurpriseMe,
  onOpenGallery,
}: HomePanelProps): React.JSX.Element {
  const { colors, shadows } = useTheme();
  const { config, setRenderer } = useRendererConfig();
  const [prompt, setPrompt] = useState('');

  // Show continue section if:
  // - There are strokes on the current canvas (hasCurrentWork)
  // - There's a saved canvas in gallery (recentCanvas)
  // - There's an active session in progress (pieceNumber > 0)
  const hasRecentWork = hasCurrentWork || recentCanvas !== null || pieceNumber > 0;

  const handleSubmitPrompt = () => {
    if (prompt.trim()) {
      onStartWithPrompt(prompt.trim());
      setPrompt('');
    }
  };

  return (
    <ScrollView
      testID="home-panel"
      style={[styles.scrollView, { backgroundColor: colors.surface }, shadows.md]}
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled"
      bounces={false}
    >
      {/* Start Drawing Section */}
      <View style={styles.startSection}>
        <Text style={[styles.sectionHeader, { color: colors.textPrimary }]}>Start Drawing</Text>

        <PromptInput
          value={prompt}
          onChange={setPrompt}
          onSubmit={handleSubmitPrompt}
          disabled={!connected}
        />

        <StylePicker
          value={drawingStyle}
          onChange={onStyleChange}
          variant="segmented"
          label="Style"
        />

        <RendererPicker
          value={config.renderer}
          onChange={setRenderer}
          label="Renderer"
        />

        <Pressable
          testID="home-surprise-me"
          style={({ pressed }) => [
            styles.surpriseMeButton,
            { backgroundColor: colors.surfaceElevated },
            pressed && { opacity: 0.8, transform: [{ scale: 0.98 }] },
            !connected && styles.disabled,
          ]}
          onPress={onSurpriseMe}
          disabled={!connected}
        >
          <Ionicons name="sparkles" size={20} color={colors.primary} />
          <Text style={[styles.surpriseMeText, { color: colors.textPrimary }]}>Surprise Me</Text>
        </Pressable>
      </View>

      {/* OR Divider */}
      {hasRecentWork && (
        <View style={styles.divider}>
          <View style={[styles.dividerLine, { backgroundColor: colors.border }]} />
          <Text style={[styles.dividerText, { color: colors.textMuted }]}>OR</Text>
          <View style={[styles.dividerLine, { backgroundColor: colors.border }]} />
        </View>
      )}

      {/* Continue Section */}
      {hasRecentWork && (
        <View style={styles.continueSection}>
          <Text style={[styles.sectionHeader, { color: colors.textPrimary }]}>
            {hasCurrentWork ? 'Continue where you left off' : 'Recent work'}
          </Text>

          <ContinueCard
            api={api}
            recentCanvas={recentCanvas}
            hasCurrentWork={hasCurrentWork}
            strokes={strokes}
            styleConfig={styleConfig}
            onContinue={onContinue}
            disabled={!connected}
          />

          <Pressable
            testID="home-gallery"
            style={({ pressed }) => [styles.galleryLink, pressed && { opacity: 0.7 }]}
            onPress={onOpenGallery}
          >
            <Ionicons name="images-outline" size={16} color={colors.textSecondary} />
            <Text style={[styles.galleryLinkText, { color: colors.textSecondary }]}>
              View Gallery{galleryCount > 0 ? ` (${galleryCount})` : ''}
            </Text>
          </Pressable>
        </View>
      )}

      {/* Connection Status */}
      {!connected && (
        <View style={styles.connectionHint}>
          <Ionicons name="cloud-offline-outline" size={14} color={colors.textMuted} />
          <Text style={[styles.connectionHintText, { color: colors.textMuted }]}>
            Connecting...
          </Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    borderRadius: borderRadius.lg,
  },
  container: {
    padding: spacing.lg,
    gap: spacing.lg,
  },
  sectionHeader: {
    ...typography.body,
    fontWeight: '600',
    marginBottom: spacing.sm,
  },
  startSection: {
    gap: spacing.md,
  },
  surpriseMeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    borderRadius: borderRadius.lg,
  },
  surpriseMeText: {
    ...typography.body,
    fontWeight: '500',
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  dividerLine: {
    flex: 1,
    height: 1,
  },
  dividerText: {
    ...typography.small,
    fontWeight: '500',
  },
  continueSection: {
    gap: spacing.sm,
  },
  galleryLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.sm,
  },
  galleryLinkText: {
    ...typography.small,
    fontWeight: '500',
  },
  disabled: {
    opacity: 0.5,
  },
  connectionHint: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  connectionHintText: {
    ...typography.small,
  },
});
