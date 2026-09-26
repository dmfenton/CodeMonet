import XCTest

/// Per the app-shell work package's acceptance checks in
/// ../ARCHITECTURE.md — real flows keyed on the `accessibilityIdentifier`s
/// from the ux spec's appendix. Two tiers:
///
/// - **Offline** (`CodeMonetOfflineUITests`): always run, need no server.
///   These exercise whatever's reachable with zero network — the Auth
///   screen's own local validation, and the app launching at all.
/// - **Live-server** (`CodeMonetLiveServerUITests`): exercise the signed-in
///   app (home, new canvas sheet, studio, gallery), which needs a real
///   `localhost:8000` dev server for the DEBUG dev-token bootstrap
///   (net-auth spec §4) to actually sign in. Gated behind
///   `CODEMONET_UITEST_LIVE_SERVER=1` so `make test-app`'s default run
///   stays offline; each test still calls `requireLiveServer()` itself so a
///   direct Xcode run of one test method fails loudly instead of silently
///   passing.
final class CodeMonetOfflineUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launch()
    }

    func testAppLaunches() throws {
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
    }

    /// Root gating (ux spec §1): no cached session and no reachable dev
    /// server -> the app settles on the Auth screen, not stuck loading.
    func testUnauthenticatedLaunchShowsAuthScreen() throws {
        let emailField = app.textFields["email-input"]
        XCTAssertTrue(emailField.waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["auth-submit-button"].exists)
    }

    /// Ux spec §3: submitting an empty email is local validation — no
    /// network call, and the "Email is required" copy has no testID
    /// (matches source: no testID on the error/success boxes).
    func testEmptyEmailShowsValidationError() throws {
        let submit = app.buttons["auth-submit-button"]
        XCTAssertTrue(submit.waitForExistence(timeout: 10))
        submit.tap()
        XCTAssertTrue(app.staticTexts["Email is required"].waitForExistence(timeout: 5))
    }

    /// Ux spec §3: typing after an error clears it (`onClearError`).
    func testTypingClearsValidationError() throws {
        let emailField = app.textFields["email-input"]
        let submit = app.buttons["auth-submit-button"]
        XCTAssertTrue(submit.waitForExistence(timeout: 10))
        submit.tap()
        XCTAssertTrue(app.staticTexts["Email is required"].waitForExistence(timeout: 5))

        emailField.tap()
        emailField.typeText("a")
        XCTAssertFalse(app.staticTexts["Email is required"].exists)
    }
}

final class CodeMonetLiveServerUITests: XCTestCase {
    private let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = false
        try requireLiveServer()
        // Documented in `CodeMonetApp.swift`: not read by the app itself,
        // but marks intent for anyone reading a test run's launch args.
        app.launchArguments = ["-devToken"]
        app.launch()
    }

    /// Ux spec §5: Home is a single scrollable card with the "Start
    /// Drawing" section and (once app-shell's toolbar entry point exists)
    /// a way into New Canvas.
    func testHomeScreenShowsStartDrawingControls() throws {
        let homePanel = app.scrollViews["home-panel"]
        XCTAssertTrue(homePanel.waitForExistence(timeout: 15), "expected to reach Home via the DEBUG dev-token bootstrap")
        XCTAssertTrue(app.textFields["home-prompt-input"].exists)
        XCTAssertTrue(app.buttons["home-prompt-submit"].exists)
        XCTAssertTrue(app.buttons["home-surprise-me"].exists)
        XCTAssertTrue(app.buttons["home-gallery"].exists)
    }

    /// Ux spec §7.2 + native improvement #1: New Canvas is a real, reachable
    /// sheet (not the RN app's unreachable one) — presented with detents
    /// from `RootView`'s app-shell-owned sheet wiring.
    func testNewCanvasSheetOpensAndStarts() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 15))

        app.buttons["home-new-canvas-button"].tap()

        // A vertical-axis `TextField` can surface as either a text field or
        // a text view depending on the SwiftUI/UIKit version underneath it —
        // match by identifier regardless of element type.
        let directionField = app.descendants(matching: .any)["new-canvas-input"]
        XCTAssertTrue(directionField.waitForExistence(timeout: 5))
        directionField.tap()
        directionField.typeText("a simple spiral")

        app.buttons["new-canvas-start-button"].tap()

        // Starting a canvas enters Studio (ux spec §1.1).
        XCTAssertTrue(app.descendants(matching: .any)["canvas-view"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any)["action-bar"].exists)
    }

    /// Ux spec §1.1: ActionBar's Home button always fully exits the studio.
    func testStudioHomeButtonReturnsHome() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 15))
        app.buttons["home-surprise-me"].tap()

        XCTAssertTrue(app.descendants(matching: .any)["action-bar"].waitForExistence(timeout: 10))
        app.buttons["action-home"].tap()

        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 10))
    }

    /// Ux spec §8 (Gallery is not a peer screen — always remembers where it
    /// came from) + §1.1 (its header Close/Home affordances).
    func testGalleryOpensFromHomeAndCloses() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 15))
        app.buttons["home-gallery"].tap()

        XCTAssertTrue(app.staticTexts["Gallery"].waitForExistence(timeout: 10))
        app.buttons["gallery-close-button"].tap()

        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 10))
    }

    private func requireLiveServer() throws {
        let flagIsSet = ProcessInfo.processInfo.environment["CODEMONET_UITEST_LIVE_SERVER"] == "1"
        try XCTSkipUnless(flagIsSet, "set CODEMONET_UITEST_LIVE_SERVER=1 with a local server running (make dev) to run this")
    }
}
