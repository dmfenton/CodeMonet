import { act, renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from './AuthContext';

function token(exp: number): string {
  const encode = (value: object): string =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  return `${encode({ alg: 'RS256', typ: 'JWT' })}.${encode({ sub: 'owner-1', exp })}.signature`;
}

function response(ok: boolean, body: object): Response {
  return { ok, json: async () => body } as Response;
}

describe('AuthContext', () => {
  const fetchMock = vi.fn<typeof fetch>();
  const wrapper = ({ children }: { children: React.ReactNode }): React.ReactElement => (
    <AuthProvider>{children}</AuthProvider>
  );

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    localStorage.clear();
    fetchMock.mockReset();
  });

  afterEach(() => vi.unstubAllGlobals());

  it('requires the provider', () => {
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used within an AuthProvider'
    );
  });

  it('starts unauthenticated without a stored session', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('restores a valid platform session through the CodeMonet user boundary', async () => {
    localStorage.setItem('auth_access_token', token(Math.floor(Date.now() / 1000) + 3600));
    fetchMock.mockResolvedValueOnce(response(true, { id: 'user-1', email: 'owner@example.com' }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    expect(result.current.user).toEqual({ id: 'user-1', email: 'owner@example.com' });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/auth/me'),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: expect.any(String) }),
      })
    );
  });

  it('rotates an expired session using the platform refresh token', async () => {
    const refreshed = token(Math.floor(Date.now() / 1000) + 3600);
    localStorage.setItem('auth_access_token', token(Math.floor(Date.now() / 1000) - 60));
    localStorage.setItem('auth_refresh_token', 'refresh-1');
    fetchMock
      .mockResolvedValueOnce(
        response(true, {
          access_token: refreshed,
          refresh_token: 'refresh-2',
          expires_in: 3600,
          token_type: 'Bearer',
        })
      )
      .mockResolvedValueOnce(response(true, { id: 'user-1', email: 'owner@example.com' }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    expect(localStorage.getItem('auth_access_token')).toBe(refreshed);
    expect(localStorage.getItem('auth_refresh_token')).toBe('refresh-2');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('https://identity.dmfenton.net/v1/oauth/token');
  });

  it('requests a PKCE authorization link from shared identity', async () => {
    fetchMock.mockResolvedValueOnce(response(true, {}));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      expect(await result.current.requestMagicLink('owner@example.com')).toEqual({ success: true });
    });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('https://identity.dmfenton.net/v1/authorization/requests');
    expect(JSON.parse(String(init?.body))).toMatchObject({
      email: 'owner@example.com',
      client_id: 'net.dmfenton.codemonet',
      redirect_uri: 'https://monet.dmfenton.net/auth/callback',
      code_challenge_method: 'S256',
    });
    expect(localStorage.getItem('auth_code_verifier')).toBeTruthy();
  });

  it('exchanges a one-time platform code and establishes the local user session', async () => {
    const accessToken = token(Math.floor(Date.now() / 1000) + 3600);
    localStorage.setItem('auth_code_verifier', 'verifier');
    fetchMock
      .mockResolvedValueOnce(
        response(true, {
          access_token: accessToken,
          refresh_token: 'refresh-token',
          expires_in: 3600,
          token_type: 'Bearer',
        })
      )
      .mockResolvedValueOnce(response(true, { id: 'user-1', email: 'owner@example.com' }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      expect(await result.current.exchangeAuthorizationCode('authorization-code')).toEqual({
        success: true,
      });
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(localStorage.getItem('auth_code_verifier')).toBeNull();
    expect(localStorage.getItem('auth_refresh_token')).toBe('refresh-token');
  });

  it('rejects a callback that did not originate on this device', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await expect(result.current.exchangeAuthorizationCode('code')).resolves.toEqual({
      success: false,
      error: 'Sign-in request expired on this device',
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('deduplicates concurrent callback delivery', async () => {
    const accessToken = token(Math.floor(Date.now() / 1000) + 3600);
    localStorage.setItem('auth_code_verifier', 'verifier');
    fetchMock
      .mockResolvedValueOnce(
        response(true, {
          access_token: accessToken,
          refresh_token: 'refresh-token',
          expires_in: 3600,
          token_type: 'Bearer',
        })
      )
      .mockResolvedValueOnce(response(true, { id: 'user-1', email: 'owner@example.com' }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const first = result.current.exchangeAuthorizationCode('authorization-code');
    const duplicate = result.current.exchangeAuthorizationCode('authorization-code');

    expect(duplicate).toBe(first);
    await expect(first).resolves.toEqual({ success: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('clears the complete local session on sign out', async () => {
    localStorage.setItem('auth_access_token', 'access');
    localStorage.setItem('auth_refresh_token', 'refresh');
    localStorage.setItem('auth_code_verifier', 'verifier');
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.signOut());

    expect(localStorage.getItem('auth_access_token')).toBeNull();
    expect(localStorage.getItem('auth_refresh_token')).toBeNull();
    expect(localStorage.getItem('auth_code_verifier')).toBeNull();
  });
});
