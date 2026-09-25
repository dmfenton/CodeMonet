import XCTest

/// Launch smoke test (per the app-shell work package's acceptance checks in
/// ../ARCHITECTURE.md). Real flows (auth, home, studio, gallery) belong to
/// their owning UI work packages, following the `testID` ->
/// `accessibilityIdentifier` carry-over table in the ux spec's appendix.
final class CodeMonetUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testAppLaunches() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
    }
}
