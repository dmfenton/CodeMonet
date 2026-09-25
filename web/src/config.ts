/**
 * Configuration for the web app.
 * SSR-compatible: handles both server and client environments.
 */

// Check if we're running on the server (no window object)
const isServer = typeof window === 'undefined';

// Check if we're in development mode
const isDev = !isServer && import.meta.env?.DEV;

export const getApiUrl = (): string => {
  // Server-side: use environment variable or default
  if (isServer) {
    return process.env.API_URL || 'http://localhost:8000';
  }

  // Client-side environment variable override
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // In dev, use Vite proxy (proxies to localhost:8000)
  if (isDev) {
    return '/api';
  }

  // In production, nginx proxies /api/* to the backend
  return '/api';
};

/**
 * Browser-facing URL for an API asset path (e.g. a gallery image_url).
 * Identical during SSR and on the client, so it is safe in rendered markup.
 */
export const getPublicAssetUrl = (path: string): string => {
  if (/^https?:\/\//.test(path)) return path;
  const base = import.meta.env.VITE_API_URL || '/api';
  return `${base.replace(/\/$/, '')}${path}`;
};

export const getWebSocketUrl = (): string => {
  // Server-side: WebSocket URLs aren't needed for SSR
  if (isServer) {
    return '';
  }

  // Environment variable override
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }

  // In dev, connect directly to backend
  if (isDev) {
    return 'ws://localhost:8000/ws';
  }

  // In production, construct WebSocket URL from current location
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
};
