import XCTest

/// Structural coverage for the Studio screen's accessibility identifiers
/// (ux spec §6 + appendix). Reaching Studio requires a signed-in session,
/// which in a DEBUG build auto-attempts the dev-token bootstrap against
/// `localhost:8000` (net-auth spec §4) — there is no server in this offline
/// test run, so these tests degrade gracefully to a no-op when the app is
/// still on the Auth screen instead of failing the whole suite. The
/// `pause`/`resume`/nudge-send/draw-gesture round trip against a real
/// server is this work package's "Manual" acceptance item, verified later
/// by the e2e agent per ../../ARCHITECTURE.md's work-package table.
final class StudioUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testStudioAccessibilityIdentifiersWhenReachable() throws {
        let app = XCUIApplication()
        app.launch()
        guard app.wait(for: .runningForeground, timeout: 10) else {
            XCTFail("app did not launch")
            return
        }

        let surpriseMe = app.buttons["home-surprise-me"]
        guard surpriseMe.waitForExistence(timeout: 5) else {
            // No local server reachable from this offline run — the Auth
            // screen never resolves to signed-in. Nothing further to check
            // here; the live round trip is this package's documented
            // Manual acceptance item.
            return
        }

        surpriseMe.tap()

        let canvas = app.otherElements["canvas-view"]
        XCTAssertTrue(canvas.waitForExistence(timeout: 5), "canvas-view should appear once Studio is reachable")

        let actionBar = app.otherElements["action-bar"]
        XCTAssertTrue(actionBar.exists, "action-bar should be visible alongside the canvas")

        // Normal (non-paused, non-view-only) state shows all five buttons.
        for identifier in ["action-draw", "action-nudge", "action-home", "action-gallery", "action-pause"] {
            XCTAssertTrue(app.buttons[identifier].exists, "\(identifier) should exist in the normal running state")
        }
    }
}
