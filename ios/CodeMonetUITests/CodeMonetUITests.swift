import XCTest

/// Per the app-shell work package's acceptance checks in
/// ../ARCHITECTURE.md — real flows keyed on the `accessibilityIdentifier`s
/// from the ux spec's appendix. Two tiers:
///
/// - **Offline** (`CodeMonetOfflineUITests`): always run, need no server.
///   These exercise whatever's reachable with zero network — the Auth
///   screen's own local validation, and the app launching at all.
/// - **Live-server** (`CodeMonetLiveServerUITests`): exercise the signed-in
///   app (home composer, studio, gallery), which needs a real
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

    /// Home: brand header, one composer (prompt, style + size chips,
    /// Surprise me, Begin), and the recent row with the Gallery link.
    func testHomeScreenShowsComposer() throws {
        let homePanel = app.scrollViews["home-panel"]
        XCTAssertTrue(homePanel.waitForExistence(timeout: 15), "expected to reach Home via the DEBUG dev-token bootstrap")
        XCTAssertTrue(element("home-prompt-input").exists)
        XCTAssertTrue(app.buttons["home-prompt-submit"].exists)
        XCTAssertFalse(app.buttons["home-prompt-submit"].isEnabled, "Begin needs a prompt")
        XCTAssertTrue(app.buttons["home-surprise-me"].exists)
        XCTAssertTrue(app.buttons["home-style-paint"].exists)
        XCTAssertTrue(app.buttons["home-style-plotter"].exists)
        XCTAssertTrue(element("home-size-menu").exists)
        XCTAssertTrue(app.buttons["home-gallery"].exists)
        XCTAssertTrue(element("home-account-menu").exists)
    }

    /// Begin starts a piece from the composer and enters Studio, whose nudge
    /// bar and pause button replace the old action bar.
    func testComposerBeginEntersStudio() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 15))
        let input = element("home-prompt-input")
        input.tap()
        input.typeText("a simple spiral")
        app.buttons["home-prompt-submit"].tap()

        XCTAssertTrue(element("canvas-view").waitForExistence(timeout: 10))
        XCTAssertTrue(element("nudge-input").exists)
        XCTAssertTrue(app.buttons["studio-pause-button"].exists)
        XCTAssertTrue(element("studio-menu").exists)
    }

    /// Studio's back button always fully exits to Home.
    func testStudioBackReturnsHome() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 15))
        app.buttons["home-surprise-me"].tap()

        XCTAssertTrue(app.buttons["studio-back-button"].waitForExistence(timeout: 10))
        app.buttons["studio-back-button"].tap()

        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 10))
    }

    /// Gallery always remembers where it came from; its back button returns there.
    func testGalleryOpensFromHomeAndCloses() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 15))
        app.buttons["home-gallery"].tap()

        XCTAssertTrue(app.staticTexts["Gallery"].waitForExistence(timeout: 10))
        app.buttons["gallery-close-button"].tap()

        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 10))
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any)[identifier]
    }

    private func requireLiveServer() throws {
        let flagIsSet = ProcessInfo.processInfo.environment["CODEMONET_UITEST_LIVE_SERVER"] == "1"
        try XCTSkipUnless(flagIsSet, "set CODEMONET_UITEST_LIVE_SERVER=1 with a local server running (make dev) to run this")
    }
}
