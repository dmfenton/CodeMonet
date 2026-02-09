/**
 * Renderer picker for switching between SVG and Freehand renderers.
 * Uses segmented control style matching StylePicker.
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { RendererType } from '@code-monet/shared';

import { spacing, borderRadius, typography, useTheme } from '../theme';

interface RendererPickerProps {
  value: RendererType;
  onChange: (renderer: RendererType) => void;
  label?: string;
}

export function RendererPicker({
  value,
  onChange,
  label,
}: RendererPickerProps): React.JSX.Element {
  const { colors } = useTheme();

  const getOptionStyle = (renderer: RendererType) => {
    const isActive = value === renderer;
    return [
      styles.optionBase,
      styles.optionSegmented,
      isActive && [styles.optionSegmentedActive, { backgroundColor: colors.surface }],
    ];
  };

  const getTextColor = (renderer: RendererType) => {
    const isActive = value === renderer;
    return isActive ? colors.primary : colors.textSecondary;
  };

  return (
    <View style={styles.container}>
      {label && <Text style={[styles.label, { color: colors.textMuted }]}>{label}</Text>}
      <View style={[styles.picker, { backgroundColor: colors.surfaceElevated }]}>
        <Pressable
          testID="renderer-svg-button"
          style={getOptionStyle('svg')}
          onPress={() => onChange('svg')}
        >
          <Ionicons name="code-slash-outline" size={18} color={getTextColor('svg')} />
          <Text style={[styles.optionText, { color: getTextColor('svg') }]}>SVG</Text>
        </Pressable>
        <Pressable
          testID="renderer-freehand-button"
          style={getOptionStyle('freehand')}
          onPress={() => onChange('freehand')}
        >
          <Ionicons name="brush-outline" size={18} color={getTextColor('freehand')} />
          <Text style={[styles.optionText, { color: getTextColor('freehand') }]}>Freehand</Text>
        </Pressable>
        <Pressable
          testID="renderer-skia-button"
          style={getOptionStyle('skia')}
          onPress={() => onChange('skia')}
        >
          <Ionicons name="speedometer-outline" size={18} color={getTextColor('skia')} />
          <Text style={[styles.optionText, { color: getTextColor('skia') }]}>Skia</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.sm,
  },
  label: {
    ...typography.small,
    fontWeight: '500',
    paddingLeft: spacing.xs,
  },
  picker: {
    flexDirection: 'row',
    borderRadius: borderRadius.lg,
    padding: spacing.xs,
  },
  optionBase: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
  },
  optionSegmented: {
    borderRadius: borderRadius.md,
    gap: spacing.sm,
  },
  optionSegmentedActive: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  optionText: {
    ...typography.body,
    fontWeight: '500',
  },
});
