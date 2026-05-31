import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import React from 'react';

// Create a valid JWT token for testing
function createTestToken(payload: { sub: string; email: string; exp: number }): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = btoa(JSON.stringify(payload));
  const signature = btoa('test-signature');
  return `${header}.${body}.${signature}`;
}

describe('AuthContext', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch);
    localStorage.clear();
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('useAuth', () => {
    it('throws error when used outside AuthProvider', () => {
      expect(() => {
        renderHook(() => useAuth());
      }).toThrow('useAuth must be used within an AuthProvider');
    });
  });

  describe('AuthProvider', () => {
    const wrapper = ({ children }: { children: React.ReactNode }): React.ReactElement => (
      <AuthProvider>{children}</AuthProvider>
    );

    it('resolves to unauthenticated when no tokens present', async () => {
      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
    });

    it('loads valid token from localStorage', async () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600; // 1 hour from now
      const token = createTestToken({ sub: '1', email: 'test@example.com', exp: futureExp });
      localStorage.setItem('auth_access_token', token);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user?.email).toBe('test@example.com');
      expect(result.current.user?.id).toBe('1');
    });

    it('treats expired token as invalid', async () => {
      const pastExp = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
      const token = createTestToken({ sub: '1', email: 'test@example.com', exp: pastExp });
      localStorage.setItem('auth_access_token', token);

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
    });

    it('signOut clears tokens and state', async () => {
      const futureExp = Math.floor(Date.now() / 1000) + 3600;
      const token = createTestToken({ sub: '1', email: 'test@example.com', exp: futureExp });
      localStorage.setItem('auth_access_token', token);
      localStorage.setItem('auth_refresh_token', 'refresh-token');

      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      act(() => {
        result.current.signOut();
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
      expect(localStorage.getItem('auth_access_token')).toBe(null);
      expect(localStorage.getItem('auth_refresh_token')).toBe(null);
    });

    describe('requestMagicLink', () => {
      it('returns success on 200 response', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => ({}),
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        let response: { success: boolean; error?: string };
        await act(async () => {
          response = await result.current.requestMagicLink('test@example.com');
        });

        expect(response!.success).toBe(true);
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('/auth/magic-link'),
          expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({ email: 'test@example.com', platform: 'web' }),
          })
        );
      });

      it('returns error on failed response', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: false,
          json: async () => ({ detail: 'Rate limit exceeded' }),
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        let response: { success: boolean; error?: string };
        await act(async () => {
          response = await result.current.requestMagicLink('test@example.com');
        });

        expect(response!.success).toBe(false);
        expect(response!.error).toBe('Rate limit exceeded');
      });

      it('returns network error on fetch failure', async () => {
        mockFetch.mockRejectedValueOnce(new Error('Network error'));

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        let response: { success: boolean; error?: string };
        await act(async () => {
          response = await result.current.requestMagicLink('test@example.com');
        });

        expect(response!.success).toBe(false);
        expect(response!.error).toBe('Network error');
      });
    });

    describe('verifyMagicLinkCode', () => {
      it('stores tokens and updates state on success', async () => {
        const futureExp = Math.floor(Date.now() / 1000) + 3600;
        const accessToken = createTestToken({
          sub: '1',
          email: 'test@example.com',
          exp: futureExp,
        });

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            access_token: accessToken,
            refresh_token: 'refresh-token',
          }),
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        let response: { success: boolean; error?: string };
        await act(async () => {
          response = await result.current.verifyMagicLinkCode('test@example.com', '123456');
        });

        expect(response!.success).toBe(true);
        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.user?.email).toBe('test@example.com');
        expect(localStorage.getItem('auth_access_token')).toBe(accessToken);
        expect(localStorage.getItem('auth_refresh_token')).toBe('refresh-token');
      });

      it('returns error on invalid code', async () => {
        mockFetch.mockResolvedValueOnce({
          ok: false,
          json: async () => ({ detail: 'Invalid or expired code' }),
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        let response: { success: boolean; error?: string };
        await act(async () => {
          response = await result.current.verifyMagicLinkCode('test@example.com', '000000');
        });

        expect(response!.success).toBe(false);
        expect(response!.error).toBe('Invalid or expired code');
        expect(result.current.isAuthenticated).toBe(false);
      });
    });

    describe('setTokensFromCallback', () => {
      it('stores tokens and updates state on valid tokens', async () => {
        const futureExp = Math.floor(Date.now() / 1000) + 3600;
        const accessToken = createTestToken({
          sub: '1',
          email: 'test@example.com',
          exp: futureExp,
        });
        const refreshToken = 'refresh-token';

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        let response: { success: boolean; error?: string };
        act(() => {
          response = result.current.setTokensFromCallback(accessToken, refreshToken);
        });

        expect(response!.success).toBe(true);
        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.user?.email).toBe('test@example.com');
        expect(localStorage.getItem('auth_access_token')).toBe(accessToken);
        expect(localStorage.getItem('auth_refresh_token')).toBe(refreshToken);
      });

      it('returns error on invalid token', async () => {
        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        let response: { success: boolean; error?: string };
        act(() => {
          response = result.current.setTokensFromCallback('invalid-token', 'refresh-token');
        });

        expect(response!.success).toBe(false);
        expect(response!.error).toBe('Invalid token received');
        expect(result.current.isAuthenticated).toBe(false);
      });
    });

    describe('token refresh', () => {
      it('refreshes expired access token with valid refresh token', async () => {
        const pastExp = Math.floor(Date.now() / 1000) - 3600; // expired
        const futureExp = Math.floor(Date.now() / 1000) + 3600; // valid
        const expiredToken = createTestToken({ sub: '1', email: 'test@example.com', exp: pastExp });
        const newToken = createTestToken({ sub: '1', email: 'test@example.com', exp: futureExp });

        localStorage.setItem('auth_access_token', expiredToken);
        localStorage.setItem('auth_refresh_token', 'valid-refresh-token');

        mockFetch.mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            access_token: newToken,
            refresh_token: 'new-refresh-token',
          }),
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        expect(result.current.isAuthenticated).toBe(true);
        expect(localStorage.getItem('auth_access_token')).toBe(newToken);
      });

      it('clears tokens when refresh fails', async () => {
        const pastExp = Math.floor(Date.now() / 1000) - 3600;
        const expiredToken = createTestToken({ sub: '1', email: 'test@example.com', exp: pastExp });

        localStorage.setItem('auth_access_token', expiredToken);
        localStorage.setItem('auth_refresh_token', 'invalid-refresh-token');

        mockFetch.mockResolvedValueOnce({
          ok: false,
          json: async () => ({ detail: 'Invalid refresh token' }),
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        expect(result.current.isAuthenticated).toBe(false);
        expect(localStorage.getItem('auth_access_token')).toBe(null);
        expect(localStorage.getItem('auth_refresh_token')).toBe(null);
      });
    });
  });
});
