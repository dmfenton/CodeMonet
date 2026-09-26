# iOS Deployment (TestFlight)

The iOS app is a native SwiftUI app (`ios/`), built from an XcodeGen-generated
project (`ios/project.yml` -> `ios/CodeMonet.xcodeproj`). See
`ios/ARCHITECTURE.md` for the module graph and `ios/Makefile` for local
build/test commands.

## Triggering a Build

Create and push a version tag to trigger a TestFlight build:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Or manually trigger via GitHub Actions -> TestFlight Deploy -> Run workflow.
The build is skipped if the tag introduces no changes under `ios/` or
`fenton-platform.lock` (pass `force: true` to override).

## How It Works

1. GitHub Actions (`macos-26`) runs on tag push
2. `xcodegen generate` regenerates `CodeMonet.xcodeproj` from `project.yml`
3. Fastlane (`ios/fastlane`) archives the app unsigned (`skip_codesigning`)
4. The immutable `platform.dmfenton.net` signing action validates entitlements and packages the IPA
5. Fastlane uploads to TestFlight

## Key Files

- `.github/workflows/testflight.yml` - CI workflow
- `ios/fastlane/Fastfile` - Build and upload lane (`beta`)
- `ios/fastlane/Appfile` - App Store Connect config
- `ios/project.yml` - XcodeGen project definition (targets, bundle id, entitlements)
- `ios/Config/{Debug,Release}.xcconfig` - API/WS base URLs baked in per configuration

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

## Versioning

Version is extracted from git tag (e.g., `v1.2.3` -> version `1.2.3`).
Build number is auto-generated from timestamp. Fastlane passes both to
`xcodebuild` as `MARKETING_VERSION`/`CURRENT_PROJECT_VERSION` xcargs.

The app owns its generated unsigned archive, provisioning profile, entitlements, and App Store
delivery. Do not add keychain setup or `codesign` here; those belong to the shared platform action.

## Local Dev Auth

DEBUG builds fall back to a dev-token bootstrap (`AuthService`, net-auth
spec §4) when no session is restored, so a Simulator build against
`localhost:8000` (see `ios/Config/Debug.xcconfig`) signs itself in without
the magic-link flow. `CodeMonetUITests` passes a `-devToken` launch argument
purely as a marker that a test expects a reachable local dev server; the app
itself doesn't gate on it.

## Production API/WS URLs

Update `ios/Config/Release.xcconfig` to point `CODE_MONET_API_BASE_URL` /
`CODE_MONET_WS_BASE_URL` at your production server, then run
`xcodegen generate` to pick up the change.
