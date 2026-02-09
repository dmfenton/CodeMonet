/**
 * Renderer Context - Provides Skia renderer configuration.
 *
 * Usage:
 *   // In App.tsx, wrap your app with RendererProvider
 *   <RendererProvider>
 *     <App />
 *   </RendererProvider>
 *
 *   // In components, use the hook to get config
 *   const { config } = useRendererConfig();
 */

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

import type { RendererConfig, RendererContextValue, RendererType } from '@code-monet/shared';
import { getDefaultConfigForRenderer } from '@code-monet/shared';

const RendererContext = createContext<RendererContextValue | null>(null);

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
    return getDefaultConfigForRenderer('skia');
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
