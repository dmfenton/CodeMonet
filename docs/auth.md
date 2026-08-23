# Authentication

Production authentication is owned by Fenton Identity at `https://identity.dmfenton.net`.
CodeMonet is an OAuth public client (`net.dmfenton.codemonet`) using authorization code flow with
PKCE. The API accepts only RS256 platform access tokens for audience `codemonet-api` and the
`fenton` household.

## Sign-in flow

1. The client creates a random PKCE verifier and stores it only on that device.
2. The client sends the email, SHA-256 challenge, client ID, and fixed callback URL to Fenton
   Identity.
3. Shared communications delivers the one-time link.
4. `/auth/callback?code=...` exchanges the code and verifier for rotating platform tokens.
5. CodeMonet verifies the access token against the shared JWKS and maps the stable platform owner
   subject to exactly one existing active CodeMonet user.

The platform access token intentionally omits email. `/auth/me` returns the app-owned user record
after the resource-server boundary succeeds. WebSocket authentication uses the same access token.

## Production boundaries

- Password, local magic-link, local code-verification, and app-local refresh endpoints return 404.
- The local HS256 token implementation remains development-only for fixtures and explicit dev
  tokens.
- The platform pin in `fenton-platform.lock` is checked out at the exact commit for CI and image
  builds.
- The iOS universal link path is `/auth/callback*` for bundle `net.dmfenton.sketchpad`.

## Configuration

Public defaults live in `code_monet.config.Settings`:

- `IDENTITY_ISSUER=https://identity.dmfenton.net`
- `IDENTITY_JWKS_URL=https://identity.dmfenton.net/.well-known/jwks.json`
- `IDENTITY_AUDIENCE=codemonet-api`
- `IDENTITY_CLIENT_ID=net.dmfenton.codemonet`
- `IDENTITY_HOUSEHOLD_ID=fenton`

`JWT_SECRET` is required only for development-only legacy tokens.
