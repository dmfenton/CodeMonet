@testable import CodeMonet
import MonetProtocol
import MonetStudio
import Testing

/// Pure-function tests for `HomeSelectors` and the easel status line.
@Suite("HomeSelectors")
struct HomeSelectorsTests {
    private static let ref = PaintingVersionRef(
        pieceNumber: 4, version: 4, assetBase: "/painting-assets/u/t/", imageWidth: 1600, imageHeight: 1200
    )

    @Test("nothing on the easel before any piece; a started blank piece stays resumable")
    func emptyEasel() throws {
        var state = StudioState()
        #expect(HomeSelectors.easel(state) == nil)
        state.pieceNumber = 3
        let easel = try #require(HomeSelectors.easel(state))
        #expect(easel.preview == .blank)
        #expect(easel.title == "Piece 3")
    }

    @Test("a painting shows its latest version, title, and a status line with version and stage")
    func paintingEasel() throws {
        var state = StudioState()
        state.pieceNumber = 4
        state.paused = false
        state.drawingStyle = .paint
        state.title = "Poplars at dusk"
        state.painting = PaintingState(base: nil, playing: Self.ref)
        state.versions = [PaintingVersionSummary(ref: Self.ref, stages: ["ground", "sky", "poplars"], ops: 318)]
        let easel = try #require(HomeSelectors.easel(state))
        #expect(easel.title == "Poplars at dusk")
        #expect(easel.preview == .painting(Self.ref))
        #expect(easel.statusLine == "painting · v4 · poplars")
        #expect(easel.isActive)
    }

    @Test("an untitled piece falls back to its prompt, then 'Piece N'")
    func titleFallback() throws {
        var state = StudioState()
        state.pieceNumber = 2
        state.prompt = "a small pond with lilies at dusk"
        #expect(try #require(HomeSelectors.easel(state)).title == "a small pond with lilies at dusk")
        #expect(try #require(HomeSelectors.easel(state)).preview == .blank)

        state.prompt = nil
        state.strokes = [Path(type: .polyline, points: [Point(x: 0, y: 0), Point(x: 5, y: 5)])]
        let easel = try #require(HomeSelectors.easel(state))
        #expect(easel.title == "Piece 2")
        #expect(easel.statusLine == "paused")
        #expect(!easel.isActive)
    }

    @Test("recent pieces are the three newest")
    func recentPieces() {
        var state = StudioState()
        state.gallery = [1, 2, 3, 4, 5].map(Self.makeEntry)
        #expect(HomeSelectors.recentPieces(state).map(\.pieceNumber) == [5, 4, 3])
    }

    @Test("canSubmit requires non-whitespace text and a connected socket")
    func canSubmitGating() {
        #expect(HomeSelectors.canSubmit(prompt: "a cat", connected: true))
        #expect(HomeSelectors.canSubmit(prompt: "a cat", connected: false) == false)
        #expect(HomeSelectors.canSubmit(prompt: "   ", connected: true) == false)
        #expect(HomeSelectors.canSubmit(prompt: "", connected: true) == false)
    }

    private static func makeEntry(_ pieceNumber: Int) -> GalleryEntry {
        GalleryEntry(
            id: "piece_\(pieceNumber)",
            createdAt: "2026-09-20T12:00:00Z",
            pieceNumber: pieceNumber,
            strokeCount: 10,
            width: 800,
            height: 600,
            drawingStyle: .plotter,
            title: nil,
            thumbnailToken: "piece_\(pieceNumber)"
        )
    }
}
