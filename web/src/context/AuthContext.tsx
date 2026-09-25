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
  /** Re-establish the session after the server rejected the current access token. */
  recoverSession: () => void;
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

/**
 * `unavailable` means no verdict (network error, 5xx such as the server's 503
 * during an identity outage): the stored session must be kept and retried.
 */
type UserLookup = { kind: 'user'; user: User } | { kind: 'rejected' } | { kind: 'unavailable' };

type SessionOutcome = 'established' | 'rejected' | 'unavailable';

const RECOVERY_RETRY_MS = { initial: 2_000, max: 30_000 } as const;

async function fetchUser(accessToken: string): Promise<UserLookup> {
  try {
    const response = await fetch(`${getApiUrl()}/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (response.status === 401 || response.status === 403) return { kind: 'rejected' };
    if (!response.ok) return { kind: 'unavailable' };
    const value = (await response.json()) as { id: string; email: string };
    return { kind: 'user', user: { id: value.id, email: value.email } };
  } catch {
    return { kind: 'unavailable' };
  }
}

function isDefinitiveRefreshRejection(response: Response): boolean {
  return response.status === 400 || response.status === 401 || response.status === 403;
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

  const recoveryTimer = useRef<number | undefined>(undefined);
  const recoveryDelay = useRef<number>(RECOVERY_RETRY_MS.initial);

  const setSignedOut = useCallback(() => {
    clearStoredSession();
    setState({ isLoading: false, isAuthenticated: false, user: null, accessToken: null });
  }, []);

  const establishSession = useCallback(
    async (tokens: PlatformTokenResponse): Promise<SessionOutcome> => {
      if (tokens.token_type !== 'Bearer' || !decodeToken(tokens.access_token)) return 'rejected';
      // Persist before the user lookup: refresh tokens rotate, so dropping these
      // during an outage would strand the session.
      storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
      storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
      const lookup = await fetchUser(tokens.access_token);
      if (lookup.kind !== 'user') return lookup.kind;
      setState({
        isLoading: false,
        isAuthenticated: true,
        user: lookup.user,
        accessToken: tokens.access_token,
      });
      return 'established';
    },
    []
  );

  const refreshSession = useCallback(async (): Promise<SessionOutcome> => {
    const refreshToken = storage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) return 'rejected';
    try {
      const response = await refreshPlatformSession(refreshToken);
      if (isDefinitiveRefreshRejection(response)) return 'rejected';
      if (!response.ok) return 'unavailable';
      return await establishSession((await response.json()) as PlatformTokenResponse);
    } catch {
      return 'unavailable';
    }
  }, [establishSession]);

  const restoreSession = useCallback(async (): Promise<SessionOutcome> => {
    const accessToken = storage.getItem(ACCESS_TOKEN_KEY);
    if (accessToken && !isTokenExpired(accessToken)) {
      const lookup = await fetchUser(accessToken);
      if (lookup.kind === 'user') {
        setState({ isLoading: false, isAuthenticated: true, user: lookup.user, accessToken });
        return 'established';
      }
      if (lookup.kind === 'unavailable') return 'unavailable';
    }
    return refreshSession();
  }, [refreshSession]);

  /** Restore until a verdict: sign out only on rejection, retry with backoff otherwise. */
  const runRecovery = useCallback(
    (attempt: () => Promise<SessionOutcome>): void => {
      window.clearTimeout(recoveryTimer.current);
      void attempt().then((outcome) => {
        if (outcome === 'established') {
          recoveryDelay.current = RECOVERY_RETRY_MS.initial;
        } else if (outcome === 'rejected') {
          setSignedOut();
        } else {
          const delay = recoveryDelay.current;
          recoveryDelay.current = Math.min(delay * 2, RECOVERY_RETRY_MS.max);
          recoveryTimer.current = window.setTimeout(() => runRecovery(restoreSession), delay);
        }
      });
    },
    [restoreSession, setSignedOut]
  );

  useEffect(() => {
    runRecovery(restoreSession);
    return (): void => window.clearTimeout(recoveryTimer.current);
  }, [runRecovery, restoreSession]);

  const recoverSession = useCallback(
    () => runRecovery(refreshSession),
    [runRecovery, refreshSession]
  );

  const signOut = useCallback(() => {
    window.clearTimeout(recoveryTimer.current);
    storage.removeItem(CODE_VERIFIER_KEY);
    setSignedOut();
  }, [setSignedOut]);

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
          const outcome = await establishSession((await response.json()) as PlatformTokenResponse);
          if (outcome === 'established') return { success: true };
          if (outcome === 'unavailable') {
            // Tokens are stored; finish sign-in once the service answers.
            runRecovery(restoreSession);
            return { success: false, error: 'Service temporarily unavailable, retrying' };
          }
          return { success: false, error: 'Identity could not be mapped to a CodeMonet user' };
        } catch {
          return { success: false, error: 'Network error' };
        }
      })();
      return exchangePromise.current;
    },
    [establishSession, runRecovery, restoreSession]
  );

  const value = useMemo(
    () => ({ ...state, signOut, recoverSession, requestMagicLink, exchangeAuthorizationCode }),
    [state, signOut, recoverSession, requestMagicLink, exchangeAuthorizationCode]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
