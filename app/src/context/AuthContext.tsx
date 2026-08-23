import {
  exchangePlatformAuthorizationCode,
  type PlatformTokenResponse,
  refreshPlatformSession,
  requestPlatformAuthorization,
} from '@code-monet/shared';
import { decode as base64Decode, encode as base64Encode } from 'base-64';
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Platform } from 'react-native';
import { getApiUrl } from '../config';

const ACCESS_TOKEN_KEY = 'auth_access_token';
const REFRESH_TOKEN_KEY = 'auth_refresh_token';
const CODE_VERIFIER_KEY = 'auth_code_verifier';

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
  signOut: () => Promise<void>;
  refreshToken: () => Promise<boolean>;
  requestMagicLink: (email: string) => Promise<{ success: boolean; error?: string }>;
  exchangeAuthorizationCode: (code: string) => Promise<{ success: boolean; error?: string }>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const storage = {
  async getItem(key: string): Promise<string | null> {
    return Platform.OS === 'web' ? localStorage.getItem(key) : SecureStore.getItemAsync(key);
  },
  async setItem(key: string, value: string): Promise<void> {
    if (Platform.OS === 'web') localStorage.setItem(key, value);
    else await SecureStore.setItemAsync(key, value);
  },
  async deleteItem(key: string): Promise<void> {
    if (Platform.OS === 'web') localStorage.removeItem(key);
    else await SecureStore.deleteItemAsync(key);
  },
};

function decodeToken(token: string): { sub: string; exp: number } | null {
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const decoded = base64Decode(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='));
    return JSON.parse(decoded) as { sub: string; exp: number };
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const decoded = decodeToken(token);
  return decoded === null || decoded.exp * 1000 < Date.now() + 30_000;
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return base64Encode(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function toBase64Url(value: string): string {
  return value.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function fetchUser(accessToken: string): Promise<User | null> {
  const response = await fetch(`${getApiUrl()}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) return null;
  const value = (await response.json()) as { id: string; email: string };
  return { id: value.id, email: value.email };
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
    await storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    await storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    setState({ isLoading: false, isAuthenticated: true, user, accessToken: tokens.access_token });
    return true;
  }, []);

  const refreshTokenInternal = useCallback(
    async (refreshTokenValue: string): Promise<boolean> => {
      try {
        const response = await refreshPlatformSession(refreshTokenValue);
        if (!response.ok) return false;
        return establishSession((await response.json()) as PlatformTokenResponse);
      } catch {
        return false;
      }
    },
    [establishSession]
  );

  useEffect(() => {
    void (async () => {
      const accessToken = await storage.getItem(ACCESS_TOKEN_KEY);
      if (accessToken && !isTokenExpired(accessToken)) {
        const user = await fetchUser(accessToken).catch(() => null);
        if (user) {
          setState({ isLoading: false, isAuthenticated: true, user, accessToken });
          return;
        }
      }
      const storedRefreshToken = await storage.getItem(REFRESH_TOKEN_KEY);
      if (storedRefreshToken && (await refreshTokenInternal(storedRefreshToken))) return;

      if (__DEV__) {
        try {
          const response = await fetch(`${getApiUrl()}/auth/dev-token`);
          if (response.ok) {
            const data = (await response.json()) as { access_token: string };
            const user = await fetchUser(data.access_token);
            if (user) {
              await storage.setItem(ACCESS_TOKEN_KEY, data.access_token);
              await storage.deleteItem(REFRESH_TOKEN_KEY);
              setState({
                isLoading: false,
                isAuthenticated: true,
                user,
                accessToken: data.access_token,
              });
              return;
            }
          }
        } catch {
          // Development server is optional during static UI work.
        }
      }

      await storage.deleteItem(ACCESS_TOKEN_KEY);
      await storage.deleteItem(REFRESH_TOKEN_KEY);
      setState({ isLoading: false, isAuthenticated: false, user: null, accessToken: null });
    })();
  }, [refreshTokenInternal]);

  const signOut = useCallback(async () => {
    await Promise.all([
      storage.deleteItem(ACCESS_TOKEN_KEY),
      storage.deleteItem(REFRESH_TOKEN_KEY),
      storage.deleteItem(CODE_VERIFIER_KEY),
    ]);
    setState({ isLoading: false, isAuthenticated: false, user: null, accessToken: null });
  }, []);

  const refreshToken = useCallback(async () => {
    const value = await storage.getItem(REFRESH_TOKEN_KEY);
    return value ? refreshTokenInternal(value) : false;
  }, [refreshTokenInternal]);

  const requestMagicLink = useCallback(async (email: string) => {
    try {
      const verifier = bytesToBase64Url(Crypto.getRandomBytes(32));
      const challenge = toBase64Url(
        await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier, {
          encoding: Crypto.CryptoEncoding.BASE64,
        })
      );
      await storage.setItem(CODE_VERIFIER_KEY, verifier);
      const response = await requestPlatformAuthorization(email, challenge);
      if (response.ok) return { success: true };
      await storage.deleteItem(CODE_VERIFIER_KEY);
      return { success: false, error: 'Failed to send magic link' };
    } catch {
      await storage.deleteItem(CODE_VERIFIER_KEY);
      return { success: false, error: 'Network error' };
    }
  }, []);

  const exchangeAuthorizationCode = useCallback(
    (code: string): Promise<{ success: boolean; error?: string }> => {
      if (exchangePromise.current) return exchangePromise.current;
      exchangePromise.current = (async (): Promise<{ success: boolean; error?: string }> => {
        const verifier = await storage.getItem(CODE_VERIFIER_KEY);
        if (!verifier) return { success: false, error: 'Sign-in request expired on this device' };
        await storage.deleteItem(CODE_VERIFIER_KEY);
        try {
          const response = await exchangePlatformAuthorizationCode(code, verifier);
          if (!response.ok) return { success: false, error: 'Invalid or expired link' };
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
    () => ({ ...state, signOut, refreshToken, requestMagicLink, exchangeAuthorizationCode }),
    [state, signOut, refreshToken, requestMagicLink, exchangeAuthorizationCode]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
