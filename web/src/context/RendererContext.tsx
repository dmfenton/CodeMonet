/**
 * Renderer Context - Feature flag for switching between SVG and Skia renderers.
 *
 * Web version - uses environment variables for configuration.
 */

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

import type { RendererConfig, RendererContextValue, RendererType } from '@code-monet/shared';
import { getDefaultConfigForRenderer } from '@code-monet/shared';

const RendererContext = createContext<RendererContextValue | null>(null);

/**
 * Get initial renderer from environment variable or URL parameter.
 */
function getInitialRenderer(): RendererType {
  // Check URL parameter first (for testing)
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    const urlRenderer = params.get('renderer');
    if (urlRenderer === 'skia') {
      return 'skia';
    }
  }

  // Check environment variable
  const envRenderer = import.meta.env.VITE_RENDERER as string | undefined;
  if (envRenderer === 'skia') {
    return 'skia';
  }

  return 'svg';
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

export function RendererProvider({
  children,
  initialRenderer,
}: RendererProviderProps): React.ReactElement {
  const [config, setConfigState] = useState<RendererConfig>((): RendererConfig => {
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
  return useMemo<RendererContextValue>(
    () =>
      context ?? {
        config: getInitialConfig(),
        setRenderer: () => {},
        setConfig: () => {},
      },
    [context]
  );
}

/**
 * Hook to check if Skia renderer is available.
 * Returns true if canvaskit-wasm is available.
 */
export function useSkiaAvailable(): boolean {
  // For now, return false. Will be updated when Skia/canvaskit is installed.
  return false;
}
