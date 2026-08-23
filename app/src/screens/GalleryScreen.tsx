/**
 * GalleryScreen - Full-screen gallery of saved canvases.
 * Replaces the previous modal approach for reliable navigation.
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { SavedCanvas } from '@code-monet/shared';
import type { ApiClient } from '../api';
import { useAuthenticatedImage } from '../hooks';
import {
  spacing,
  borderRadius,
  typography,
  useTheme,
  type ColorScheme,
  type ShadowScheme,
} from '../theme';

export interface GalleryScreenProps {
  api: ApiClient;
  canvases: SavedCanvas[];
  onClose: () => void;
  onSelect: (pieceNumber: number) => void;
  onHome: () => void;
  /** Whether the gallery was opened from studio (shows home button) */
  showHomeButton: boolean;
}

// Grid configuration
const NUM_COLUMNS = 2;
const GRID_GAP = spacing.md;
const HORIZONTAL_PADDING = spacing.lg;

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

interface GalleryItemProps {
  api: ApiClient;
  canvas: SavedCanvas;
  thumbnailSize: number;
  pieceNumber: number;
  onSelect: (pieceNumber: number) => void;
  colors: ColorScheme;
  shadows: ShadowScheme;
}

function GalleryItem({
  api,
  canvas,
  thumbnailSize,
  pieceNumber,
  onSelect,
  colors,
  shadows,
}: GalleryItemProps): React.JSX.Element {
  const [nativeLoading, setNativeLoading] = useState(true);
  const [error, setError] = useState(false);
  const imageSize = thumbnailSize - spacing.sm * 2;

  const thumbnailPath = canvas.thumbnail_token
    ? `/gallery/thumbnail/${canvas.thumbnail_token}.png`
    : undefined;

  const { source: thumbnailSource, loading: hookLoading } =
    useAuthenticatedImage(api, thumbnailPath);

  const loading = hookLoading || nativeLoading;

  const handlePress = useCallback(() => {
    onSelect(pieceNumber);
  }, [onSelect, pieceNumber]);

  return (
    <Pressable
      style={({ pressed }) => [
        styles.item,
        { backgroundColor: colors.surface, width: thumbnailSize },
        shadows.sm,
        pressed && { opacity: 0.8, transform: [{ scale: 0.98 }] },
      ]}
      onPress={handlePress}
    >
      <View
        style={[
          styles.thumbnailContainer,
          { width: imageSize, height: imageSize, backgroundColor: colors.canvasBackground },
        ]}
      >
        {loading && !error && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator size="small" color={colors.textMuted} />
          </View>
        )}
        {error ? (
          <View style={styles.errorOverlay}>
            <Ionicons name="image-outline" size={32} color={colors.textMuted} />
          </View>
        ) : thumbnailSource ? (
          <Image
            source={thumbnailSource}
            style={{ width: imageSize, height: imageSize }}
            resizeMode="contain"
            onLoadStart={() => setNativeLoading(true)}
            onLoadEnd={() => setNativeLoading(false)}
            onError={() => {
              setNativeLoading(false);
              setError(true);
            }}
          />
        ) : null}
      </View>
      <View style={styles.itemInfo}>
        <Text style={[styles.itemTitle, { color: colors.textPrimary }]} numberOfLines={1}>
          {canvas.title || `#${canvas.piece_number}`}
        </Text>
        <Text style={[styles.itemMeta, { color: colors.textMuted }]}>
          {canvas.title ? `#${canvas.piece_number} · ` : ''}{formatDate(canvas.created_at)}
        </Text>
      </View>
    </Pressable>
  );
}

export function GalleryScreen({
  api,
  canvases,
  onClose,
  onSelect,
  onHome,
  showHomeButton,
}: GalleryScreenProps): React.JSX.Element {
  const { colors, shadows } = useTheme();
  const { width: screenWidth } = useWindowDimensions();

  const availableWidth = screenWidth - HORIZONTAL_PADDING * 2 - GRID_GAP * (NUM_COLUMNS - 1);
  const thumbnailSize = Math.floor(availableWidth / NUM_COLUMNS);

  const sortedCanvases = useMemo(() => [...canvases].reverse(), [canvases]);

  const renderItem = useCallback(
    ({ item }: { item: SavedCanvas }) => (
      <GalleryItem
        api={api}
        canvas={item}
        thumbnailSize={thumbnailSize}
        pieceNumber={item.piece_number}
        onSelect={onSelect}
        colors={colors}
        shadows={shadows}
      />
    ),
    [api, thumbnailSize, onSelect, colors, shadows]
  );

  const keyExtractor = useCallback((item: SavedCanvas) => item.id, []);

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={[styles.header, { borderBottomColor: colors.border }]}>
        {showHomeButton ? (
          <Pressable style={styles.headerButton} onPress={onHome}>
            <Ionicons name="home-outline" size={22} color={colors.textPrimary} />
          </Pressable>
        ) : (
          <View style={styles.headerButton} />
        )}
        <Text style={[styles.title, { color: colors.textPrimary }]}>Gallery</Text>
        <Pressable style={styles.headerButton} onPress={onClose}>
          <Ionicons name="close" size={24} color={colors.textPrimary} />
        </Pressable>
      </View>

      {canvases.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="images-outline" size={64} color={colors.textMuted} />
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            No saved artwork yet
          </Text>
          <Text style={[styles.emptyHint, { color: colors.textMuted }]}>
            Tap &quot;New&quot; to save the current canvas and start fresh
          </Text>
        </View>
      ) : (
        <FlatList
          data={sortedCanvases}
          keyExtractor={keyExtractor}
          renderItem={renderItem}
          numColumns={NUM_COLUMNS}
          contentContainerStyle={styles.grid}
          columnWrapperStyle={styles.row}
          showsVerticalScrollIndicator={false}
        />
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
  title: {
    ...typography.heading,
  },
  headerButton: {
    padding: spacing.sm,
  },
  grid: {
    padding: HORIZONTAL_PADDING,
    paddingTop: spacing.lg,
  },
  row: {
    gap: GRID_GAP,
    marginBottom: GRID_GAP,
  },
  item: {
    borderRadius: borderRadius.lg,
    padding: spacing.sm,
    alignItems: 'center',
  },
  thumbnailContainer: {
    borderRadius: borderRadius.md,
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingOverlay: {
    position: 'absolute',
    inset: 0,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorOverlay: {
    position: 'absolute',
    inset: 0,
    justifyContent: 'center',
    alignItems: 'center',
  },
  itemInfo: {
    width: '100%',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  itemTitle: {
    ...typography.caption,
    fontWeight: '600',
  },
  itemMeta: {
    ...typography.small,
  },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  emptyText: {
    ...typography.body,
    marginTop: spacing.sm,
  },
  emptyHint: {
    ...typography.small,
    textAlign: 'center',
  },
});
