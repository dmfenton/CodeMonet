# iOS Deployment (TestFlight)

## Triggering a Build

Create and push a version tag to trigger a TestFlight build:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Or manually trigger via GitHub Actions -> TestFlight Deploy -> Run workflow.

## How It Works

1. GitHub Actions (`macos-26`) runs on tag push
2. `expo prebuild` generates native iOS project
3. Fastlane builds an unsigned archive
4. The immutable `platform.dmfenton.net` signing action validates entitlements and packages the IPA
5. Fastlane uploads to TestFlight

## Key Files

- `.github/workflows/testflight.yml` - CI workflow
- `app/fastlane/Fastfile` - Build and upload lanes
- `app/fastlane/Appfile` - App Store Connect config
- `app/app.config.js` - Dynamic versioning from env vars

## Required GitHub Secrets

| Secret                           | Description                                  |
| -------------------------------- | -------------------------------------------- |
| `APP_STORE_CONNECT_API_KEY_ID`   | App Store Connect API key ID                 |
| `APP_STORE_CONNECT_ISSUER_ID`    | App Store Connect issuer ID                  |
| `APP_STORE_CONNECT_API_KEY_P8`   | .p8 key file contents                        |
| `IOS_DISTRIBUTION_CERT_P12`      | Base64-encoded .p12 certificate              |
| `IOS_DISTRIBUTION_CERT_PASSWORD` | Certificate password                         |
| `IOS_PROVISIONING_PROFILE`       | Base64-encoded .mobileprovision              |
| `APPLE_TEAM_ID`                  | 10-char Apple team ID                        |
| `APPLE_ID`                       | Apple Developer email                        |
| `ITC_TEAM_ID`                    | App Store Connect team ID                    |
| `SENTRY_ORG`                     | Sentry organization slug                     |
| `SENTRY_PROJECT`                 | Sentry project slug                          |
| `SENTRY_AUTH_TOKEN`              | Sentry auth token for source maps (optional) |

## Versioning

Version is extracted from git tag (e.g., `v1.2.3` -> version `1.2.3`).
Build number is auto-generated from timestamp.

The app owns its generated unsigned archive, provisioning profile, entitlements, and App Store
delivery. Do not add keychain setup or `codesign` here; those belong to the shared platform action.

## Production WebSocket URL

Update `EXPO_PUBLIC_WS_URL` in `.github/workflows/testflight.yml` to point to your production server.
