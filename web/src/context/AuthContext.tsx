import {
  base64Url,
  exchangePlatformAuthorizationCode,
  type PlatformTokenResponse,
  refreshPlatformSession,
  requestPlatformAuthorization,
} from '@code-monet/shared';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { getApiUrl } from '../config';

const isServer = typeof window === 'undefined';
const ACCESS_TOKEN_KEY = 'auth_access_token';
const REFRESH_TOKEN_KEY = 'auth_refresh_token';
const CODE_VERIFIER_KEY = 'auth_code_verifier';

const storage = {
  getItem: (key: string): string | null => (isServer ? null : localStorage.getItem(key)),
  setItem: (key: string, value: string): void => {
    if (!isServer) localStorage.setItem(key, value);
  },
  removeItem: (key: string): void => {
    if (!isServer) localStorage.removeItem(key);
  },
};

export interface User {
  id: string;
  email: string;
}

export interface AuthState {
  isLoading: boolean;
  isAuthenticated: boolean;
  user: User | null;
  accessToken: string | null;
}

export interface AuthContextValue extends AuthState {
  signOut: () => void;
  requestMagicLink: (email: string) => Promise<{ success: boolean; error?: string }>;
  exchangeAuthorizationCode: (code: string) => Promise<{ success: boolean; error?: string }>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function decodeToken(token: string): { sub: string; exp: number } | null {
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='))) as {
      sub: string;
      exp: number;
    };
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const decoded = decodeToken(token);
  return decoded === null || decoded.exp * 1000 < Date.now() + 30_000;
}

async function fetchUser(accessToken: string): Promise<User | null> {
  const response = await fetch(`${getApiUrl()}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) return null;
  const value = (await response.json()) as { id: string; email: string };
  return { id: value.id, email: value.email };
}

function clearStoredSession(): void {
  storage.removeItem(ACCESS_TOKEN_KEY);
  storage.removeItem(REFRESH_TOKEN_KEY);
}

function errorMessage(response: Response, fallback: string): Promise<string> {
  return response
    .json()
    .then((value: unknown) => {
      if (typeof value !== 'object' || value === null) return fallback;
      const body = value as { detail?: unknown; error?: unknown };
      if (typeof body.detail === 'string') return body.detail;
      if (typeof body.error === 'string') return body.error;
      return fallback;
    })
    .catch(() => fallback);
}

export function AuthProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const exchangePromise = useRef<Promise<{ success: boolean; error?: string }> | undefined>(
    undefined
  );
  const [state, setState] = useState<AuthState>({
    isLoading: true,
    isAuthenticated: false,
    user: null,
    accessToken: null,
  });

  const establishSession = useCallback(async (tokens: PlatformTokenResponse): Promise<boolean> => {
    if (tokens.token_type !== 'Bearer' || !decodeToken(tokens.access_token)) return false;
    const user = await fetchUser(tokens.access_token);
    if (!user) return false;
    storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    setState({ isLoading: false, isAuthenticated: true, user, accessToken: tokens.access_token });
    return true;
  }, []);

  const refreshTokenInternal = useCallback(
    async (refreshToken: string): Promise<boolean> => {
      try {
        const response = await refreshPlatformSession(refreshToken);
        if (!response.ok) return false;
        return establishSession((await response.json()) as PlatformTokenResponse);
      } catch {
        return false;
      }
    },
    [establishSession]
  );

  useEffect(() => {
    void (async (): Promise<void> => {
      const accessToken = storage.getItem(ACCESS_TOKEN_KEY);
      if (accessToken && !isTokenExpired(accessToken)) {
        const user = await fetchUser(accessToken).catch(() => null);
        if (user) {
          setState({ isLoading: false, isAuthenticated: true, user, accessToken });
          return;
        }
      }
      const refreshToken = storage.getItem(REFRESH_TOKEN_KEY);
      if (refreshToken && (await refreshTokenInternal(refreshToken))) return;
      clearStoredSession();
      setState({ isLoading: false, isAuthenticated: false, user: null, accessToken: null });
    })();
  }, [refreshTokenInternal]);

  const signOut = useCallback(() => {
    clearStoredSession();
    storage.removeItem(CODE_VERIFIER_KEY);
    setState({ isLoading: false, isAuthenticated: false, user: null, accessToken: null });
  }, []);

  const requestMagicLink = useCallback(async (email: string) => {
    try {
      const verifierBytes = new Uint8Array(32);
      crypto.getRandomValues(verifierBytes);
      const verifier = base64Url(verifierBytes);
      const challenge = base64Url(
        new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)))
      );
      storage.setItem(CODE_VERIFIER_KEY, verifier);
      const response = await requestPlatformAuthorization(email, challenge);
      if (response.ok) return { success: true };
      storage.removeItem(CODE_VERIFIER_KEY);
      return { success: false, error: await errorMessage(response, 'Failed to send magic link') };
    } catch {
      storage.removeItem(CODE_VERIFIER_KEY);
      return { success: false, error: 'Network error' };
    }
  }, []);

  const exchangeAuthorizationCode = useCallback(
    (code: string): Promise<{ success: boolean; error?: string }> => {
      if (exchangePromise.current) return exchangePromise.current;
      exchangePromise.current = (async (): Promise<{ success: boolean; error?: string }> => {
        const verifier = storage.getItem(CODE_VERIFIER_KEY);
        if (!verifier) return { success: false, error: 'Sign-in request expired on this device' };
        storage.removeItem(CODE_VERIFIER_KEY);
        try {
          const response = await exchangePlatformAuthorizationCode(code, verifier);
          if (!response.ok) {
            return {
              success: false,
              error: await errorMessage(response, 'Invalid or expired link'),
            };
          }
          const success = await establishSession((await response.json()) as PlatformTokenResponse);
          return success
            ? { success: true }
            : { success: false, error: 'Identity could not be mapped to a CodeMonet user' };
        } catch {
          return { success: false, error: 'Network error' };
        }
      })();
      return exchangePromise.current;
    },
    [establishSession]
  );

  const value = useMemo(
    () => ({ ...state, signOut, requestMagicLink, exchangeAuthorizationCode }),
    [state, signOut, requestMagicLink, exchangeAuthorizationCode]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
