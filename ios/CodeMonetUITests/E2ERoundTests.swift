import XCTest

/// Ad-hoc, round-3 E2E driver used to manually verify the full composed
/// flow (auth -> home -> new canvas -> studio -> pause/resume -> nudge ->
/// finish -> gallery -> open piece) against a real local server, for BOTH
/// drawing styles (program painting + plotter). Not part of the normal
/// `make test-app` suite — invoked directly via `xcodebuild test
/// -only-testing:CodeMonetUITests/E2ERoundTests`. Screenshots are captured
/// externally (via `xcrun simctl io screenshot`) on a timer while this
/// runs; the sleeps below exist to give that external capture loop frames
/// worth looking at, not to synchronize correctness (which is verified via
/// UI-tree waits).
final class E2ERoundTests: XCTestCase {
    private let app = XCUIApplication()

    override func setUpWithError() throws {
        continueAfterFailure = true
        // Ad-hoc verification harness: assumes a real localhost:8000 dev
        // server is already up (round-3 E2E task), same precondition
        // `CodeMonetLiveServerUITests` gates behind an env var that does
        // not reliably propagate through `xcodebuild test-without-building`.
        app.launchArguments = ["-devToken"]
        app.launch()
    }

    /// Round-4 regression check for round-3 Finding 1 ("New Canvas sheet can
    /// fire Start before the user finishes, discarding the typed
    /// direction"). Reproduces the exact tap sequence that mis-fired
    /// before: open sheet -> pick a style -> tap the direction field ->
    /// type. If the fix (settle-delay gating the action bar) holds, the
    /// sheet should still be open and the field should contain what we
    /// typed.
    func testNewCanvasSheetDoesNotTapThrough() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 20), "home-panel")
        app.buttons["home-new-canvas-button"].tap()

        let styleButton = app.buttons["new-canvas-style-paint-button"]
        XCTAssertTrue(styleButton.waitForExistence(timeout: 5), "new-canvas-style-paint-button")
        styleButton.tap()

        let directionField = app.textViews["new-canvas-input"].exists
            ? app.textViews["new-canvas-input"]
            : app.textFields["new-canvas-input"]
        XCTAssertTrue(directionField.waitForExistence(timeout: 5), "new-canvas-input")
        directionField.tap()
        directionField.typeText("a lighthouse in a storm")

        // The known-bad behavior was the sheet dismissing and Studio
        // appearing within ~1-2s of the tap, before Start was ever
        // pressed. Give it a beat, then assert we're still on the sheet
        // with our text intact (not silently in Studio on an undirected
        // canvas).
        Thread.sleep(forTimeInterval: 2)
        XCTAssertTrue(directionField.exists, "new-canvas-input should still exist (sheet still open) after typing")
        XCTAssertFalse(app.descendants(matching: .any)["action-bar"].exists, "should NOT have tapped through into Studio's action-bar")

        let startButton = app.buttons["new-canvas-start-button"]
        if startButton.waitForExistence(timeout: 3), startButton.isEnabled {
            startButton.tap()
            XCTAssertTrue(app.descendants(matching: .any)["canvas-view"].waitForExistence(timeout: 15), "canvas-view after explicit Start tap")
        }
    }

    func testPaintStyleFullFlow() throws {
        try runFullFlow(style: "paint", prompt: "draw a simple sunset over the ocean")
    }

    func testPlotterStyleFullFlow() throws {
        try runFullFlow(style: "plotter", prompt: "draw a simple sunset over the ocean")
    }

    /// Quick, targeted check (no new agent turn): open a specific legacy
    /// `format: "strokes"` gallery piece and a specific `format: "raster"`
    /// one, to compare their full-view rendering directly.
    func testOpenSpecificGalleryPieces() throws {
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 20), "home-panel")
        app.buttons["home-gallery"].tap()
        XCTAssertTrue(app.staticTexts["Gallery"].waitForExistence(timeout: 10), "Gallery title")
        Thread.sleep(forTimeInterval: 2)

        // Legacy paint piece, pre-program-painting, modest stroke count
        // (format: strokes).
        let legacyItem = app.descendants(matching: .any)["gallery-item-179"]
        XCTAssertTrue(legacyItem.waitForExistence(timeout: 10), "gallery-item-179")
        legacyItem.tap()
        Thread.sleep(forTimeInterval: 3)
        XCTAssertTrue(app.descendants(matching: .any)["canvas-view"].waitForExistence(timeout: 10), "canvas-view (legacy)")
        Thread.sleep(forTimeInterval: 3)

        app.buttons["action-home"].tap()
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 10), "home-panel after legacy view")

        // Raster (program-painted) piece (format: raster).
        app.buttons["home-gallery"].tap()
        XCTAssertTrue(app.staticTexts["Gallery"].waitForExistence(timeout: 10), "Gallery title 2")
        Thread.sleep(forTimeInterval: 2)
        let rasterItem = app.descendants(matching: .any)["gallery-item-180"]
        XCTAssertTrue(rasterItem.waitForExistence(timeout: 10), "gallery-item-180")
        rasterItem.tap()
        Thread.sleep(forTimeInterval: 3)
        XCTAssertTrue(app.descendants(matching: .any)["canvas-view"].waitForExistence(timeout: 10), "canvas-view (raster)")
        Thread.sleep(forTimeInterval: 2)
    }

    // MARK: -

    private func runFullFlow(style: String, prompt: String) throws {
        // Home. Drives the flow through Home's own inline prompt+style
        // controls (`home-prompt-input`/`home-prompt-submit`/`style-*`)
        // rather than the "New Canvas" sheet (`home-new-canvas-button` ->
        // `NewCanvasView`): the sheet's own path reproducibly mis-starts
        // (see round-3 report, "New Canvas sheet" finding) before Start is
        // ever tapped, which would block this driver rather than exercise
        // the rest of the composed flow it exists to verify.
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 20), "home-panel [\(style)]")

        let styleButton = app.buttons["style-\(style)-button"]
        XCTAssertTrue(styleButton.waitForExistence(timeout: 5), "style button [\(style)]")
        styleButton.tap()

        let promptField = app.textFields["home-prompt-input"]
        XCTAssertTrue(promptField.waitForExistence(timeout: 5), "home-prompt-input [\(style)]")
        promptField.tap()
        promptField.typeText(prompt)

        let submitButton = app.buttons["home-prompt-submit"]
        XCTAssertTrue(submitButton.waitForExistence(timeout: 5), "home-prompt-submit [\(style)]")
        submitButton.tap()

        // Studio
        XCTAssertTrue(app.descendants(matching: .any)["canvas-view"].waitForExistence(timeout: 15), "canvas-view [\(style)]")
        XCTAssertTrue(app.descendants(matching: .any)["action-bar"].waitForExistence(timeout: 10), "action-bar [\(style)]")

        // Let thinking text / first strokes stream in.
        Thread.sleep(forTimeInterval: 8)

        let liveStatus = app.descendants(matching: .any)["live-status"]
        XCTAssertTrue(liveStatus.waitForExistence(timeout: 20), "live-status should appear while agent is active [\(style)]")

        // Pause
        let pauseButton = app.buttons["action-pause"]
        XCTAssertTrue(pauseButton.waitForExistence(timeout: 10), "action-pause [\(style)]")
        pauseButton.tap()
        Thread.sleep(forTimeInterval: 3)

        // Resume
        pauseButton.tap()
        Thread.sleep(forTimeInterval: 3)

        // Nudge
        let nudgeButton = app.buttons["action-nudge"]
        if nudgeButton.waitForExistence(timeout: 5), nudgeButton.isEnabled {
            nudgeButton.tap()
            let nudgeInput = app.descendants(matching: .any)["nudge-input"]
            if nudgeInput.waitForExistence(timeout: 5) {
                nudgeInput.tap()
                nudgeInput.typeText("add more warm colors")
                let sendButton = app.buttons["nudge-send-button"]
                if sendButton.exists, sendButton.isEnabled {
                    sendButton.tap()
                } else {
                    app.buttons["nudge-close-button"].tap()
                }
            }
        }
        Thread.sleep(forTimeInterval: 3)

        // Wait for the agent to go idle (LiveStatusView renders nothing
        // when idle with no buffered content — its disappearance is the
        // documented "agent finished" signal).
        let idlePredicate = NSPredicate(format: "exists == false")
        let idleExpectation = XCTNSPredicateExpectation(predicate: idlePredicate, object: liveStatus)
        let idleResult = XCTWaiter().wait(for: [idleExpectation], timeout: 240)
        if idleResult != .completed {
            XCTAttachment(string: "live-status did not clear within 240s for style=\(style); piece may still be drawing.")
                .lifetime = .keepAlways
        }
        Thread.sleep(forTimeInterval: 2)

        // Home
        let homeButton = app.buttons["action-home"]
        XCTAssertTrue(homeButton.waitForExistence(timeout: 5), "action-home [\(style)]")
        homeButton.tap()
        XCTAssertTrue(app.scrollViews["home-panel"].waitForExistence(timeout: 10), "back to home-panel [\(style)]")

        // Gallery
        app.buttons["home-gallery"].tap()
        XCTAssertTrue(app.staticTexts["Gallery"].waitForExistence(timeout: 10), "Gallery title [\(style)]")
        Thread.sleep(forTimeInterval: 2)

        let firstGalleryItem = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'gallery-item-'"))
            .firstMatch
        if firstGalleryItem.waitForExistence(timeout: 5) {
            firstGalleryItem.tap()
            Thread.sleep(forTimeInterval: 2)
        }
    }
}
