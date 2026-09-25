@testable import CodeMonet
import MonetProtocol
import MonetStudio
import Testing

/// Pure-function tests for `HomeSelectors` (ux spec §5.2, §5.4) — built
/// against plain `StudioState` fixtures, no live `StudioStore`/socket
/// needed.
@Suite("HomeSelectors")
struct HomeSelectorsTests {
    @Test("no recent work when canvas is empty, no gallery, no session")
    func noRecentWork() {
        let state = StudioState()
        #expect(HomeSelectors.hasRecentWork(state) == false)
        #expect(HomeSelectors.continueCardKind(state) == .none)
    }

    @Test("live strokes alone count as recent work")
    func liveStrokesCountAsRecentWork() {
        var state = StudioState()
        state.strokes = [Path(type: .polyline, points: [Point(x: 0, y: 0), Point(x: 10, y: 10)])]
        #expect(HomeSelectors.hasRecentWork(state))
        #expect(HomeSelectors.hasCurrentWork(state))
        #expect(HomeSelectors.continueSectionHeader(state) == "Continue where you left off")
    }

    @Test("gallery entry alone counts as recent work, but not current work")
    func galleryAloneCountsAsRecentWork() {
        var state = StudioState()
        state.gallery = [Self.makeEntry(pieceNumber: 3, title: "Sunset")]
        #expect(HomeSelectors.hasRecentWork(state))
        #expect(HomeSelectors.hasCurrentWork(state) == false)
        #expect(HomeSelectors.continueSectionHeader(state) == "Recent work")
    }

    @Test("active session with zero strokes still counts as recent work")
    func activeSessionAloneCountsAsRecentWork() {
        var state = StudioState()
        state.pieceNumber = 2
        #expect(HomeSelectors.hasRecentWork(state))
    }

    @Test("continueCardKind is .live with a live preview when strokes exist")
    func continueCardKindLiveWithStrokes() {
        var state = StudioState()
        state.strokes = [Path(type: .polyline, points: [Point(x: 1, y: 1), Point(x: 2, y: 2)])]
        state.canvasWidth = 800
        state.canvasHeight = 600

        guard case let .live(strokes, width, height, _, title) = HomeSelectors.continueCardKind(state) else {
            Issue.record("expected .live")
            return
        }
        #expect(strokes.count == 1)
        #expect(width == 800)
        #expect(height == 600)
        #expect(title == "Current Drawing")
    }

    @Test("continueCardKind is .completed when only a gallery entry exists")
    func continueCardKindCompletedFromGallery() {
        var state = StudioState()
        state.gallery = [Self.makeEntry(pieceNumber: 5, title: nil)]

        guard case let .completed(entry) = HomeSelectors.continueCardKind(state) else {
            Issue.record("expected .completed")
            return
        }
        #expect(entry.pieceNumber == 5)
    }

    @Test("continueCardKind prefers live strokes over a stale gallery thumbnail")
    func continueCardKindPrefersLiveOverGallery() {
        var state = StudioState()
        state.strokes = [Path(type: .polyline, points: [Point(x: 0, y: 0), Point(x: 5, y: 5)])]
        state.gallery = [Self.makeEntry(pieceNumber: 1, title: "Old piece")]

        guard case .live = HomeSelectors.continueCardKind(state) else {
            Issue.record("expected .live even with a gallery entry present")
            return
        }
    }

    @Test("canSubmit requires non-whitespace text and a connected socket")
    func canSubmitGating() {
        #expect(HomeSelectors.canSubmit(prompt: "a cat", connected: true))
        #expect(HomeSelectors.canSubmit(prompt: "a cat", connected: false) == false)
        #expect(HomeSelectors.canSubmit(prompt: "   ", connected: true) == false)
        #expect(HomeSelectors.canSubmit(prompt: "", connected: true) == false)
    }

    private static func makeEntry(pieceNumber: Int, title: String?) -> GalleryEntry {
        GalleryEntry(
            id: "piece_\(pieceNumber)",
            createdAt: "2026-09-20T12:00:00Z",
            pieceNumber: pieceNumber,
            strokeCount: 10,
            width: 800,
            height: 600,
            drawingStyle: .plotter,
            title: title,
            thumbnailToken: "piece_\(pieceNumber)"
        )
    }
}
