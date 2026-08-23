/**
 * Auth callback route for deep links.
 * Handles the Fenton Identity OAuth callback.
 */

import { Redirect, useLocalSearchParams } from 'expo-router';
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { useAuth } from '../../src/context/AuthContext';

export default function AuthCallback() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const { exchangeAuthorizationCode } = useAuth();
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;
    if (!code) {
      setError('Missing authorization code');
      setDone(true);
      return;
    }
    void exchangeAuthorizationCode(code).then((result) => {
      setError(result.success ? null : (result.error ?? 'Authentication failed'));
      setDone(true);
    });
  }, [code, exchangeAuthorizationCode]);

  if (!done) {
    return (
      <View>
        <ActivityIndicator />
        <Text>Signing you in…</Text>
      </View>
    );
  }
  return <Redirect href={error ? `/?auth_error=${encodeURIComponent(error)}` : '/'} />;
}
