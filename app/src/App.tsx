/**
 * Code Monet - Main Application
 * An AI-powered drawing experience inspired by impressionist art.
 *
 * This file is now simplified to just composition - all business logic
 * lives in contexts (StudioContext, NavigationContext).
 */

import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
  StatusBar,
  StyleSheet,
  View,
} from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  forwardLogs,
  initLogForwarder,
  startLogSession,
} from '@code-monet/shared';

import {
  DebugOverlay,
  NewCanvasModal,
  NudgeModal,
  SplashScreen,
} from './components';
import { getApiUrl } from './config';
import {
  NavigationProvider,
  StudioProvider,
  useAuth,
  useNavigation,
  useStudio,
} from './context';
import { useDeepLinks } from './hooks';
import { AuthScreen, GalleryScreen, HomeScreen, StudioScreen } from './screens';
import { spacing, useTheme } from './theme';
import { tracer } from './utils/tracing';

/**
 * Main app content - uses contexts for all state and actions.
 * This component is responsible for rendering screens and modals.
 */
function MainApp(): React.JSX.Element {
  const { colors, isDark } = useTheme();
  const { screen, closeGallery, galleryFromStudio } = useNavigation();
  const {
    canvasState,
    agentStatus,
    currentTool,
    wsConnected,
    activeModal,
    closeModal,
    api,
    actions,
  } = useStudio();

  const [showSplash, setShowSplash] = useState(true);

  return (
    <GestureHandlerRootView style={[styles.root, { backgroundColor: colors.background }]}>
      <StatusBar
        barStyle={isDark ? 'light-content' : 'dark-content'}
        backgroundColor={colors.background}
      />

      {/* Splash Screen */}
      {showSplash && <SplashScreen onFinish={() => setShowSplash(false)} />}

      <SafeAreaView
        style={[styles.container, { backgroundColor: colors.background }]}
        edges={['top', 'left', 'right']}
      >
        <DebugOverlay
          data={{
            inStudio: screen === 'studio',
            paused: canvasState.paused,
            status: agentStatus,
            strokes: canvasState.strokes.length,
            pending: canvasState.performance.buffer.filter(i => i.type === 'strokes').length,
            thinking: canvasState.thinking.length,
            ws: wsConnected,
            gallery: canvasState.gallery.length,
          }}
        />

        <View style={styles.content}>
          {screen === 'gallery' ? (
            <GalleryScreen
              api={api}
              canvases={canvasState.gallery}
              onClose={closeGallery}
              onSelect={actions.handleGallerySelect}
              onHome={actions.handleGalleryToHome}
              showHomeButton={galleryFromStudio}
            />
          ) : screen === 'studio' ? (
            <StudioScreen
              canvasState={canvasState}
              agentStatus={agentStatus}
              currentTool={currentTool}
              wsConnected={wsConnected}
              galleryCount={canvasState.gallery.length}
              viewingPiece={canvasState.viewingPiece}
              onAction={actions.handleStudioAction}
              onStrokeStart={actions.handleStrokeStart}
              onStrokeMove={actions.handleStrokeMove}
              onStrokeEnd={actions.handleStrokeEnd}
            />
          ) : (
            <HomeScreen
              api={api}
              wsConnected={wsConnected}
              hasCurrentWork={canvasState.strokes.length > 0}
              pieceNumber={canvasState.pieceNumber}
              gallery={canvasState.gallery}
              drawingStyle={canvasState.drawingStyle}
              strokes={canvasState.strokes}
              canvasWidth={canvasState.canvasWidth}
              canvasHeight={canvasState.canvasHeight}
              styleConfig={canvasState.styleConfig}
              onStyleChange={actions.handleStyleChange}
              onContinue={actions.handleContinue}
              onStartWithPrompt={actions.handleStartWithPrompt}
              onSurpriseMe={actions.handleSurpriseMe}
              onOpenGallery={() => actions.handleStudioAction({ type: 'gallery' })}
            />
          )}
        </View>

        {/* Modals */}
        <NudgeModal
          visible={activeModal === 'nudge'}
          onClose={closeModal}
          onSend={actions.handleNudgeSend}
        />

        <NewCanvasModal
          visible={activeModal === 'newCanvas'}
          currentStyle={canvasState.drawingStyle}
          onClose={closeModal}
          onStart={actions.handleNewCanvasStart}
        />
      </SafeAreaView>
    </GestureHandlerRootView>
  );
}

/**
 * App content with auth routing.
 * Handles deep links and shows appropriate screen based on auth state.
 */
function AppContent(): React.JSX.Element {
  const { colors } = useTheme();
  const { isLoading, isAuthenticated, verifyMagicLink, setTokensFromCallback } = useAuth();

  // Handle deep links for magic link authentication
  const { verifyingMagicLink, magicLinkError, clearError } = useDeepLinks({
    verifyMagicLink,
    setTokensFromCallback,
  });

  // Show loading screen while checking auth or verifying magic link
  if (isLoading || verifyingMagicLink) {
    return (
      <GestureHandlerRootView style={[styles.root, { backgroundColor: colors.background }]}>
        <View style={[styles.loadingContainer, { backgroundColor: colors.background }]}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      </GestureHandlerRootView>
    );
  }

  // Show auth screen if not authenticated
  if (!isAuthenticated) {
    return <AuthScreen magicLinkError={magicLinkError} onClearError={clearError} />;
  }

  // Show main app with navigation and studio providers
  return (
    <NavigationProvider>
      <StudioProvider>
        <MainApp />
      </StudioProvider>
    </NavigationProvider>
  );
}

/**
 * Root app component.
 * Initializes tracing and app state tracking.
 */
export default function App(): React.JSX.Element {
  // Initialize tracing and log forwarding on app mount
  useEffect(() => {
    // Initialize log forwarder (only in dev mode)
    if (__DEV__) {
      initLogForwarder(getApiUrl());
      forwardLogs();
      void startLogSession('app-start');
    }

    // Record app launch
    tracer.recordEvent('app.launch');

    // Start auto-flushing traces every 10 seconds
    tracer.startAutoFlush(10000);

    // Track app state changes (foreground/background)
    const subscription = AppState.addEventListener('change', (nextAppState) => {
      if (nextAppState === 'active') {
        tracer.recordEvent('app.foreground');
      } else if (nextAppState === 'background') {
        tracer.recordEvent('app.background');
        // Flush traces when going to background
        tracer.flush().catch(() => {});
      }
    });

    return () => {
      subscription.remove();
      tracer.stopAutoFlush();
      // Final flush on unmount
      tracer.flush().catch(() => {});
    };
  }, []);

  // Providers are in _layout.tsx for expo-router compatibility
  return <AppContent />;
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  container: {
    flex: 1,
  },
  content: {
    flex: 1,
    paddingHorizontal: spacing.sm,
    paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
});
