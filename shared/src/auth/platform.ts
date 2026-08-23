export const PLATFORM_IDENTITY_URL = 'https://identity.dmfenton.net';
export const PLATFORM_CLIENT_ID = 'net.dmfenton.codemonet';
export const PLATFORM_REDIRECT_URI = 'https://monet.dmfenton.net/auth/callback';

export interface PlatformTokenResponse {
  access_token: string;
  token_type: 'Bearer';
  expires_in: number;
  refresh_token: string;
}

export function base64Url(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

export async function requestPlatformAuthorization(
  email: string,
  codeChallenge: string
): Promise<Response> {
  return fetch(`${PLATFORM_IDENTITY_URL}/v1/authorization/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      client_id: PLATFORM_CLIENT_ID,
      redirect_uri: PLATFORM_REDIRECT_URI,
      code_challenge: codeChallenge,
      code_challenge_method: 'S256',
    }),
  });
}

export async function exchangePlatformAuthorizationCode(
  code: string,
  codeVerifier: string
): Promise<Response> {
  return fetch(`${PLATFORM_IDENTITY_URL}/v1/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      client_id: PLATFORM_CLIENT_ID,
      redirect_uri: PLATFORM_REDIRECT_URI,
      code,
      code_verifier: codeVerifier,
    }),
  });
}

export async function refreshPlatformSession(refreshToken: string): Promise<Response> {
  return fetch(`${PLATFORM_IDENTITY_URL}/v1/oauth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'refresh_token',
      client_id: PLATFORM_CLIENT_ID,
      refresh_token: refreshToken,
    }),
  });
}
