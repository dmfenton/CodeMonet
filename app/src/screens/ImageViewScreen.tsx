/**
 * ImageViewScreen - Simple full-screen view of a completed gallery piece.
 * Shows the artwork statically without any studio controls.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { DrawingStyleConfig, Path, SavedCanvas } from '@code-monet/shared';
import { getStyleConfig, PLOTTER_STYLE } from '@code-monet/shared';

import type { ApiClient } from '../api';
import { Canvas } from '../components';
import { spacing, borderRadius, typography, useTheme } from '../theme';

export interface ImageViewScreenProps {
  api: ApiClient;
  pieceNumber: number;
  gallery: SavedCanvas[];
  onBack: () => void;
  onHome: () => void;
}

const noop = () => {};

export function ImageViewScreen({
  api,
  pieceNumber,
  gallery,
  onBack,
  onHome,
}: ImageViewScreenProps): React.JSX.Element {
  const { colors, shadows } = useTheme();
  const [strokes, setStrokes] = useState<Path[]>([]);
  const [styleConfig, setStyleConfig] = useState<DrawingStyleConfig>(PLOTTER_STYLE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const canvasEntry = gallery.find((c) => c.piece_number === pieceNumber);
  const title = canvasEntry?.title || `Piece #${pieceNumber}`;

  const fetchStrokes = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const response = await api.fetch(`/gallery/${pieceNumber}/strokes`);
      if (response.ok) {
        const data = await response.json();
        setStrokes(data.strokes);
        if (data.style_config) {
          setStyleConfig(data.style_config);
        } else if (data.drawing_style) {
          setStyleConfig(getStyleConfig(data.drawing_style));
        }
      } else {
        setError(true);
      }
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [api, pieceNumber]);

  useEffect(() => {
    void fetchStrokes();
  }, [fetchStrokes]);

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      {/* Header */}
      <View style={[styles.header, { borderBottomColor: colors.border }]}>
        <Pressable style={styles.headerButton} onPress={onBack}>
          <Ionicons name="arrow-back" size={24} color={colors.textPrimary} />
        </Pressable>
        <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={1}>
          {title}
        </Text>
        <Pressable style={styles.headerButton} onPress={onHome}>
          <Ionicons name="home-outline" size={22} color={colors.textPrimary} />
        </Pressable>
      </View>

      {/* Content */}
      <View style={styles.content}>
        {loading ? (
          <View style={styles.centered}>
            <ActivityIndicator size="large" color={colors.primary} />
          </View>
        ) : error ? (
          <View style={styles.centered}>
            <Ionicons name="alert-circle-outline" size={48} color={colors.textMuted} />
            <Text style={[styles.errorText, { color: colors.textSecondary }]}>
              Failed to load artwork
            </Text>
            <Pressable
              style={[styles.retryButton, { backgroundColor: colors.surface }, shadows.sm]}
              onPress={() => void fetchStrokes()}
            >
              <Text style={[styles.retryText, { color: colors.primary }]}>Retry</Text>
            </Pressable>
          </View>
        ) : (
          <View style={styles.canvasContainer}>
            <Canvas
              strokes={strokes}
              currentStroke={[]}
              agentStroke={[]}
              penPosition={null}
              penDown={false}
              drawingEnabled={false}
              styleConfig={styleConfig}
              showIdleAnimation={false}
              onStrokeStart={noop}
              onStrokeMove={noop}
              onStrokeEnd={noop}
            />
          </View>
        )}
      </View>

      {/* Metadata footer */}
      {canvasEntry && !loading && !error && (
        <View style={[styles.footer, { borderTopColor: colors.border }]}>
          <Text style={[styles.metaText, { color: colors.textMuted }]}>
            #{canvasEntry.piece_number}
          </Text>
          <Text style={[styles.metaText, { color: colors.textMuted }]}>
            {canvasEntry.stroke_count} strokes
          </Text>
          <Text style={[styles.metaText, { color: colors.textMuted }]}>
            {new Date(canvasEntry.created_at).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
  },
  headerButton: {
    padding: spacing.sm,
  },
  title: {
    ...typography.heading,
    flex: 1,
    textAlign: 'center',
    marginHorizontal: spacing.sm,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
  },
  canvasContainer: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
  },
  errorText: {
    ...typography.body,
  },
  retryButton: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderRadius: borderRadius.md,
  },
  retryText: {
    ...typography.body,
    fontWeight: '600',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderTopWidth: 1,
  },
  metaText: {
    ...typography.small,
  },
});
