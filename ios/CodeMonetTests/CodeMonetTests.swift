@testable import CodeMonet
import FentonMobileCore
import Foundation
import MonetProtocol
import MonetStudio
import Testing

/// Smoke coverage proving the app target links against MonetKit correctly.
/// Feature-specific tests belong with their owning work package (see
/// ../ARCHITECTURE.md).
@Suite("CodeMonet app target")
struct CodeMonetSmokeTests {
    @Test("AppScreen starts on home")
    @MainActor
    func navigationStartsOnHome() {
        let navigation = NavigationState()
        #expect(navigation.screen == .home)
    }

    @Test("StudioReducer is reachable from the app target")
    func reducerReachable() {
        let state = StudioReducer.reduce(StudioState(), .clear)
        #expect(state.strokes.isEmpty)
    }
}

/// Navigation.swift (ux spec §1: Gallery "remembers where it came from").
@Suite("NavigationState")
struct NavigationStateTests {
    @Test("openGallery records where it was opened from")
    @MainActor
    func openGalleryRecordsOrigin() {
        let navigation = NavigationState()
        navigation.openGallery(from: .studio)
        #expect(navigation.screen == .gallery)
        #expect(navigation.galleryOpenedFrom == .studio)
    }

    @Test("closeGallery returns to whichever screen opened it")
    @MainActor
    func closeGalleryReturnsToOrigin() {
        let navigation = NavigationState()
        navigation.openGallery(from: .home)
        navigation.closeGallery()
        #expect(navigation.screen == .home)

        navigation.openGallery(from: .studio)
        navigation.closeGallery()
        #expect(navigation.screen == .studio)
    }

    @Test("activeModal defaults to nil and tracks New Canvas")
    @MainActor
    func activeModalDefaultsToNil() {
        let navigation = NavigationState()
        #expect(navigation.activeModal == nil)
        navigation.activeModal = .newCanvas
        #expect(navigation.activeModal == .newCanvas)
    }
}

/// RootView.swift's deep-link failure copy (ux spec §3). Pure mapping, no
/// I/O — exercised directly against the same error types
/// `AuthenticationController.exchangeAuthorizationCode` can throw.
@Suite("MagicLinkDeepLinkError")
struct MagicLinkDeepLinkErrorTests {
    @Test("invalid/unauthorized authorization code reads as an invalid link")
    func invalidCode() {
        #expect(MagicLinkDeepLinkError.message(for: AuthenticationClientError.invalidAuthorizationCode) == "Invalid or expired link")
        #expect(MagicLinkDeepLinkError.message(for: AuthenticationClientError.unauthorized) == "Invalid or expired link")
    }

    @Test("a lost PKCE verifier reads as an expired sign-in request")
    func missingPendingAuthorization() {
        let message = MagicLinkDeepLinkError.message(for: AuthenticationClientError.missingPendingAuthorization)
        #expect(message == "Sign-in request expired on this device")
    }

    @Test("a transport failure reads as a network error")
    func transportFailure() {
        #expect(MagicLinkDeepLinkError.message(for: MobileTransportFailure.noConnection) == "Network error")
        #expect(MagicLinkDeepLinkError.message(for: MobileAPIError.transport(.timedOut)) == "Network error")
    }

    @Test("an unrecognized error falls back to the invalid-link copy")
    func unrecognizedErrorFallsBack() {
        struct OtherError: Error {}
        #expect(MagicLinkDeepLinkError.message(for: OtherError()) == "Invalid or expired link")
    }
}

/// AuthView.swift's `requestMagicLink` failure copy (ux spec §3).
@Suite("AuthRequestErrorPresentation")
struct AuthRequestErrorPresentationTests {
    @Test("a transport failure reads as a network error")
    func transportFailure() {
        #expect(AuthRequestErrorPresentation.message(for: MobileAPIError.transport(.noConnection)) == "Network error")
    }

    @Test("a known API-layer failure falls back to the default auth-failure copy")
    func apiLayerFailure() {
        #expect(AuthRequestErrorPresentation.message(for: MobileAPIError.unauthorized) == "Authentication failed")
        #expect(AuthRequestErrorPresentation.message(for: MobileAPIError.http(statusCode: 500)) == "Authentication failed")
        #expect(AuthRequestErrorPresentation.message(for: MobileAPIError.notFound) == "Authentication failed")
    }

    @Test("a truly unexpected error gets the generic exception copy")
    func unexpectedError() {
        struct OtherError: Error {}
        #expect(AuthRequestErrorPresentation.message(for: OtherError()) == "An unexpected error occurred")
    }
}

/// RootView.swift's universal-link parser (net-auth spec §5.1) — the exact
/// host/path/scheme match matters, since anything looser would let an
/// arbitrary link exchange a stolen authorization code.
@Suite("CodeMonetAuthDeepLink")
struct CodeMonetAuthDeepLinkTests {
    @Test("matches the platform universal link with a code")
    func matchesUniversalLink() throws {
        let url = try #require(URL(string: "https://monet.dmfenton.net/auth/callback?code=abc123"))
        guard case let .authorizationCode(code) = CodeMonetAuthDeepLink.parser.parse(url) else {
            Issue.record("expected an authorization code outcome")
            return
        }
        #expect(code == "abc123")
    }

    @Test("ignores a matching path on the wrong host")
    func ignoresWrongHost() throws {
        let url = try #require(URL(string: "https://evil.example.com/auth/callback?code=abc123"))
        #expect(isUnhandled(CodeMonetAuthDeepLink.parser.parse(url)))
    }

    @Test("ignores the custom scheme (net-auth spec §5.2: no handler)")
    func ignoresCustomScheme() throws {
        let url = try #require(URL(string: "codemonet://auth/callback?code=abc123"))
        #expect(isUnhandled(CodeMonetAuthDeepLink.parser.parse(url)))
    }

    @Test("ignores the universal link with no code query item")
    func ignoresMissingCode() throws {
        let url = try #require(URL(string: "https://monet.dmfenton.net/auth/callback"))
        #expect(isUnhandled(CodeMonetAuthDeepLink.parser.parse(url)))
    }

    /// `DeepLinkOutcome` isn't `Equatable` (its `Route` case may carry an
    /// arbitrary app-supplied type), so tests pattern-match instead.
    private func isUnhandled(_ outcome: DeepLinkOutcome<Never>) -> Bool {
        if case .unhandled = outcome { return true }
        return false
    }
}
