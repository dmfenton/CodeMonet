/**
 * Renderer Context - Feature flag for switching between SVG and Skia renderers.
 *
 * Usage:
 *   // In App.tsx, wrap your app with RendererProvider
 *   <RendererProvider>
 *     <App />
 *   </RendererProvider>
 *
 *   // In components, use the hook to get config or switch renderers
 *   const { config, setRenderer } = useRendererConfig();
 *   setRenderer('skia'); // Switch to Skia renderer
 */

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import Constants from 'expo-constants';

import type { RendererConfig, RendererContextValue, RendererType } from '@code-monet/shared';
import { getDefaultConfigForRenderer } from '@code-monet/shared';

const RendererContext = createContext<RendererContextValue | null>(null);

/**
 * Get initial renderer from environment variable.
 */
function getInitialRenderer(): RendererType {
  const envRenderer = Constants.expoConfig?.extra?.renderer as string | undefined;
  if (envRenderer === 'svg') {
    return 'svg';
  }
  if (envRenderer === 'freehand') {
    return 'freehand';
  }
  return 'skia';
}

/**
 * Get initial config based on environment.
 */
function getInitialConfig(): RendererConfig {
  const renderer = getInitialRenderer();
  return getDefaultConfigForRenderer(renderer);
}

interface RendererProviderProps {
  children: React.ReactNode;
  /** Override initial renderer (useful for testing) */
  initialRenderer?: RendererType;
}

export function RendererProvider({ children, initialRenderer }: RendererProviderProps) {
  const [config, setConfigState] = useState<RendererConfig>(() => {
    if (initialRenderer) {
      return getDefaultConfigForRenderer(initialRenderer);
    }
    return getInitialConfig();
  });

  const setRenderer = useCallback((type: RendererType) => {
    setConfigState(getDefaultConfigForRenderer(type));
  }, []);

  const setConfig = useCallback((partial: Partial<RendererConfig>) => {
    setConfigState((prev) => ({ ...prev, ...partial }));
  }, []);

  const value = useMemo<RendererContextValue>(
    () => ({
      config,
      setRenderer,
      setConfig,
    }),
    [config, setRenderer, setConfig]
  );

  return <RendererContext.Provider value={value}>{children}</RendererContext.Provider>;
}

/**
 * Hook to access renderer configuration.
 *
 * @throws Error if used outside of RendererProvider
 */
export function useRendererConfig(): RendererContextValue {
  const context = useContext(RendererContext);
  if (!context) {
    throw new Error('useRendererConfig must be used within a RendererProvider');
  }
  return context;
}

/**
 * Hook to check if Skia renderer is available.
 * Returns true if react-native-skia is installed and loaded.
 */
export function useSkiaAvailable(): boolean {
  try {
    require('@shopify/react-native-skia');
    return true;
  } catch {
    return false;
  }
}
