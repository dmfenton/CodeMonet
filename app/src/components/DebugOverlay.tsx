/**
 * Debug overlay for diagnosing render loops and state changes.
 * Only visible in development mode (__DEV__).
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

export interface DebugOverlayProps {
  data: Record<string, string | number | boolean | null>;
  visible?: boolean;
}

/**
 * Transparent overlay showing key app state values.
 * Useful for debugging render loops and state synchronization.
 */
export const DebugOverlay = React.memo(function DebugOverlay({
  data,
  visible = false,
}: DebugOverlayProps): React.JSX.Element | null {
  if (!__DEV__ || !visible) return null;

  return (
    <View pointerEvents="none" style={styles.container}>
      {Object.entries(data).map(([key, val]) => (
        <Text key={key} style={styles.text}>
          {key}: {String(val)}
        </Text>
      ))}
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    backgroundColor: 'rgba(0,0,0,0.85)',
    padding: 6,
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 999,
  },
  text: {
    color: '#0f0',
    fontFamily: 'monospace',
    fontSize: 10,
  },
});
