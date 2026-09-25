import MonetProtocol
import MonetStudio
import Testing
@testable import CodeMonet

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
