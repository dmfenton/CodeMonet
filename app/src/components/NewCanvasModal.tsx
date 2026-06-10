/**
 * Bottom sheet modal for starting a new canvas with optional direction.
 */

import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { DrawingStyleType } from '@code-monet/shared';
import { spacing, borderRadius, typography, useTheme } from '../theme';
import { StylePicker } from './StylePicker';

interface NewCanvasModalProps {
  visible: boolean;
  currentStyle: DrawingStyleType;
  onClose: () => void;
  onStart: (direction?: string, style?: DrawingStyleType, canvas?: CanvasDimensions) => void;
}

interface CanvasDimensions {
  canvas_width: number;
  canvas_height: number;
}

interface CanvasProfile {
  id: string;
  label: string;
  width: number;
  height: number;
}

const CANVAS_PROFILES: CanvasProfile[] = [
  { id: 'standard', label: 'Standard', width: 800, height: 600 },
  { id: 'masthead', label: 'Masthead', width: 1200, height: 420 },
  { id: 'square', label: 'Square', width: 800, height: 800 },
  { id: 'portrait', label: 'Portrait', width: 600, height: 900 },
  { id: 'wide', label: 'Wide', width: 1200, height: 600 },
];

const DIRECTION_SUGGESTIONS = [
  'A serene landscape',
  'Abstract shapes',
  'Something playful',
  'Geometric patterns',
  'Flowing curves',
  'Bold and dramatic',
];

const MAX_LENGTH = 200;

export function NewCanvasModal({
  visible,
  currentStyle,
  onClose,
  onStart,
}: NewCanvasModalProps): React.JSX.Element {
  const { colors, shadows } = useTheme();
  const [text, setText] = useState('');
  const [selectedStyle, setSelectedStyle] = useState<DrawingStyleType>(currentStyle);
  const [selectedProfileId, setSelectedProfileId] = useState(CANVAS_PROFILES[0]!.id);
  const selectedProfile =
    CANVAS_PROFILES.find((profile) => profile.id === selectedProfileId) || CANVAS_PROFILES[0]!;
  const selectedCanvas = {
    canvas_width: selectedProfile.width,
    canvas_height: selectedProfile.height,
  };

  // Reset style when modal opens with current style
  React.useEffect(() => {
    if (visible) {
      setSelectedStyle(currentStyle);
    }
  }, [visible, currentStyle]);

  const handleStart = () => {
    const direction = text.trim() || undefined;
    onStart(direction, selectedStyle, selectedCanvas);
    setText('');
    onClose();
  };

  const handleSkip = () => {
    onStart(undefined, selectedStyle, selectedCanvas);
    setText('');
    onClose();
  };

  const handleCancel = () => {
    setText('');
    onClose();
  };

  const handleSuggestion = (suggestion: string) => {
    setText(suggestion);
  };

  const remainingChars = MAX_LENGTH - text.length;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={styles.keyboardView}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <Pressable style={styles.overlay} onPress={handleCancel} />

        <View style={[styles.sheet, { backgroundColor: colors.surface }, shadows.lg]}>
          {/* Handle */}
          <View style={styles.handleContainer}>
            <View style={[styles.handle, { backgroundColor: colors.border }]} />
          </View>

          {/* Header */}
          <View style={styles.header}>
            <View>
              <Text style={[styles.title, { color: colors.textPrimary }]}>New Canvas</Text>
              <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                Give the agent a direction, or let it decide
              </Text>
            </View>
            <Pressable style={styles.closeButton} onPress={handleCancel}>
              <Ionicons name="close" size={24} color={colors.textMuted} />
            </Pressable>
          </View>

          {/* Quick suggestions */}
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.suggestionsContainer}
            contentContainerStyle={styles.suggestionsContent}
          >
            {DIRECTION_SUGGESTIONS.map((suggestion) => (
              <Pressable
                key={suggestion}
                style={[styles.suggestionChip, { backgroundColor: colors.surfaceElevated }]}
                onPress={() => handleSuggestion(suggestion)}
              >
                <Text style={[styles.suggestionText, { color: colors.textSecondary }]}>
                  {suggestion}
                </Text>
              </Pressable>
            ))}
          </ScrollView>

          {/* Style Picker */}
          <View style={styles.stylePickerContainer}>
            <StylePicker
              value={selectedStyle}
              onChange={setSelectedStyle}
              variant="pills"
              label="Style"
              testIDPrefix="new-canvas-style"
            />
          </View>

          <View style={styles.profileContainer}>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.profileContent}
            >
              {CANVAS_PROFILES.map((profile) => {
                const selected = profile.id === selectedProfileId;
                return (
                  <Pressable
                    key={profile.id}
                    style={[
                      styles.profileChip,
                      {
                        backgroundColor: selected ? colors.primary : colors.surfaceElevated,
                      },
                    ]}
                    onPress={() => setSelectedProfileId(profile.id)}
                  >
                    <Text
                      style={[
                        styles.profileText,
                        { color: selected ? colors.textOnPrimary : colors.textSecondary },
                      ]}
                    >
                      {profile.label}
                    </Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>

          {/* Input */}
          <View style={styles.inputContainer}>
            <TextInput
              testID="new-canvas-input"
              style={[
                styles.input,
                { backgroundColor: colors.surfaceElevated, color: colors.textPrimary },
              ]}
              value={text}
              onChangeText={(t) => setText(t.slice(0, MAX_LENGTH))}
              placeholder="Describe what to draw..."
              placeholderTextColor={colors.textMuted}
              multiline
              maxLength={MAX_LENGTH}
            />
            <Text
              style={[
                styles.charCount,
                { color: colors.textMuted },
                remainingChars < 20 && { color: colors.warning },
              ]}
            >
              {remainingChars}
            </Text>
          </View>

          {/* Actions */}
          <View style={styles.actions}>
            <Pressable
              style={({ pressed }) => [
                styles.skipButton,
                { backgroundColor: colors.surfaceElevated },
                pressed && styles.buttonPressed,
              ]}
              onPress={handleSkip}
            >
              <Text style={[styles.skipButtonText, { color: colors.textSecondary }]}>
                Let Agent Decide
              </Text>
            </Pressable>

            <Pressable
              testID="new-canvas-start-button"
              style={({ pressed }) => [
                styles.startButton,
                { backgroundColor: text.trim() ? colors.primary : colors.surfaceElevated },
                pressed && styles.buttonPressed,
              ]}
              onPress={handleStart}
            >
              <Ionicons
                name="brush"
                size={18}
                color={text.trim() ? colors.textOnPrimary : colors.textMuted}
              />
              <Text
                style={[
                  styles.startButtonText,
                  { color: text.trim() ? colors.textOnPrimary : colors.textMuted },
                ]}
              >
                Start
              </Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  keyboardView: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
  },
  sheet: {
    borderTopLeftRadius: borderRadius.xl,
    borderTopRightRadius: borderRadius.xl,
    paddingBottom: spacing['2xl'],
  },
  handleContainer: {
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  handle: {
    width: 40,
    height: 4,
    borderRadius: 2,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.lg,
  },
  title: {
    ...typography.heading,
    marginBottom: spacing.xs,
  },
  subtitle: {
    ...typography.caption,
  },
  closeButton: {
    padding: spacing.xs,
  },
  suggestionsContainer: {
    marginBottom: spacing.lg,
  },
  suggestionsContent: {
    paddingHorizontal: spacing.xl,
    gap: spacing.sm,
  },
  suggestionChip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.full,
    marginRight: spacing.sm,
  },
  suggestionText: {
    ...typography.caption,
  },
  inputContainer: {
    marginHorizontal: spacing.xl,
    marginBottom: spacing.lg,
    position: 'relative',
  },
  input: {
    borderRadius: borderRadius.md,
    padding: spacing.lg,
    paddingBottom: spacing['2xl'],
    ...typography.body,
    minHeight: 100,
    textAlignVertical: 'top',
  },
  charCount: {
    position: 'absolute',
    bottom: spacing.md,
    right: spacing.md,
    ...typography.small,
  },
  actions: {
    flexDirection: 'row',
    paddingHorizontal: spacing.xl,
    gap: spacing.md,
  },
  skipButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.lg,
    borderRadius: borderRadius.lg,
  },
  skipButtonText: {
    ...typography.body,
    fontWeight: '600',
  },
  startButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.lg,
    borderRadius: borderRadius.lg,
    gap: spacing.sm,
  },
  startButtonText: {
    ...typography.body,
    fontWeight: '600',
  },
  buttonPressed: {
    opacity: 0.8,
    transform: [{ scale: 0.98 }],
  },
  stylePickerContainer: {
    paddingHorizontal: spacing.xl,
    marginBottom: spacing.lg,
  },
  profileContainer: {
    marginBottom: spacing.lg,
  },
  profileContent: {
    paddingHorizontal: spacing.xl,
    gap: spacing.sm,
  },
  profileChip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.full,
    marginRight: spacing.sm,
  },
  profileText: {
    ...typography.caption,
    fontWeight: '600',
  },
});
