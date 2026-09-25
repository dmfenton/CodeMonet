# Code Monet iOS — build/test entry points. See ARCHITECTURE.md for the
# module graph and what each command actually exercises.

.PHONY: generate build test-kit test-app clean

# Regenerate CodeMonet.xcodeproj from project.yml. Run this after editing
# project.yml, adding/removing files, or after a builder's PR adds files
# xcodegen needs to pick up (xcodegen globs directories, so most new files
# under an already-listed `sources` path need no project.yml change at all —
# only new *targets*/dependencies/settings do).
generate:
	xcodegen generate

# Full simulator build, unsigned (matches CI / the architect's verification
# command). Requires `generate` to have been run at least once (or after any
# project.yml change).
build: generate
	xcodebuild -project CodeMonet.xcodeproj -scheme CodeMonet \
		-destination 'generic/platform=iOS Simulator' \
		build CODE_SIGNING_ALLOWED=NO

# MonetKit's own test suite — plain `swift test`, macOS, no simulator. This
# is the fast inner loop for protocol/studio/performer/render/networking
# logic; prefer it over `test-app` while iterating.
test-kit:
	cd MonetKit && swift test

# Full app-target test run (CodeMonetTests + CodeMonetUITests) on a booted
# simulator. Slower than test-kit; run before a PR, not on every save.
test-app: generate
	xcodebuild -project CodeMonet.xcodeproj -scheme CodeMonet \
		-destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
		test

clean:
	rm -rf CodeMonet.xcodeproj
	cd MonetKit && swift package clean
