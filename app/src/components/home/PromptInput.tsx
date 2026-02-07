/**
 * PromptInput - Text input for entering drawing prompts.
 */

import React from 'react';
import { Keyboard, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { spacing, borderRadius, typography, useTheme } from '../../theme';

const MAX_PROMPT_LENGTH = 200;

interface PromptInputProps {
  value: string;
  onChange: (text: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

export function PromptInput({
  value,
  onChange,
  onSubmit,
  disabled = false,
}: PromptInputProps): React.JSX.Element {
  const { colors } = useTheme();
  const canSubmit = Boolean(value.trim()) && !disabled;

  const handleSubmit = () => {
    if (canSubmit) {
      onSubmit();
      Keyboard.dismiss();
    }
  };

  return (
    <View
      style={[
        styles.container,
        { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
      ]}
    >
      <TextInput
        testID="home-prompt-input"
        style={[styles.input, { color: colors.textPrimary }]}
        value={value}
        onChangeText={(t) => onChange(t.slice(0, MAX_PROMPT_LENGTH))}
        placeholder="Describe your next piece…"
        placeholderTextColor={colors.textMuted}
        returnKeyType="go"
        onSubmitEditing={handleSubmit}
      />
      <Pressable
        testID="home-prompt-submit"
        style={[
          styles.submitButton,
          { backgroundColor: canSubmit ? colors.primary : colors.surfaceElevated },
        ]}
        onPress={handleSubmit}
        disabled={!canSubmit}
      >
        <Ionicons
          name="arrow-forward"
          size={20}
          color={canSubmit ? colors.textOnPrimary : colors.textMuted}
        />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    paddingLeft: spacing.md,
    paddingRight: spacing.xs,
  },
  input: {
    flex: 1,
    ...typography.body,
    paddingVertical: spacing.md,
  },
  submitButton: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
