/**
 * Root layout for expo-router.
 * Wraps all routes with theme and auth providers.
 */

import * as Sentry from '@sentry/react-native';
import Constants, { AppOwnership } from 'expo-constants';
import { Stack, useNavigationContainerRef } from 'expo-router';
import { useEffect } from 'react';

import { AuthProvider } from '../src/context/AuthContext';
import { ThemeProvider } from '../src/theme';

// Check if running in Expo Go (native features limited)
const isExpoGo = Constants.appOwnership === AppOwnership.Expo;

// Create navigation integration for route tracking
const navigationIntegration = Sentry.reactNavigationIntegration({
  enableTimeToInitialDisplay: !isExpoGo,
});

// Initialize Sentry for crash reporting
Sentry.init({
  dsn: 'https://cbc0025fc6dcd2b55265bc8b4e429b20@o4510700455591936.ingest.us.sentry.io/4510700456443904',
  enabled: !__DEV__,
  tracesSampleRate: 0.2,
  integrations: [navigationIntegration],
  enableNativeFramesTracking: !isExpoGo,
  enableAutoSessionTracking: true,
});

function RootLayout() {
  const navigationRef = useNavigationContainerRef();

  useEffect(() => {
    if (navigationRef) {
      navigationIntegration.registerNavigationContainer(navigationRef);
    }
  }, [navigationRef]);

  return (
    <ThemeProvider>
      <AuthProvider>
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="index" />
          <Stack.Screen name="auth/verify" />
          <Stack.Screen name="auth/callback" />
        </Stack>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default Sentry.wrap(RootLayout);
