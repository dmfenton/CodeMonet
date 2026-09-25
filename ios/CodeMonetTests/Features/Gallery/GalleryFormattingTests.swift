@testable import CodeMonet
import MonetProtocol
import Testing

@Suite("GalleryFormatting")
struct GalleryFormattingTests {
    @Test("title falls back to piece number when untitled")
    func titleFallback() {
        let untitled = Self.makeEntry(pieceNumber: 7, title: nil)
        #expect(GalleryFormatting.title(for: untitled) == "#7")

        let named = Self.makeEntry(pieceNumber: 7, title: "Sunset")
        #expect(GalleryFormatting.title(for: named) == "Sunset")
    }

    @Test("meta line includes piece number only when a title exists, to avoid repeating it")
    func metaLineAvoidsRedundancy() {
        let named = Self.makeEntry(pieceNumber: 12, title: "Sunset")
        #expect(GalleryFormatting.metaLine(for: named).hasPrefix("#12 · "))

        let untitled = Self.makeEntry(pieceNumber: 12, title: nil)
        #expect(!GalleryFormatting.metaLine(for: untitled).contains("#12"))
    }

    @Test("shortDate has no year and no time, matching the RN 'Sep 25' format")
    func shortDateFormat() {
        let formatted = GalleryFormatting.shortDate("2026-09-25T14:30:00.000Z")
        #expect(!formatted.isEmpty)
        #expect(!formatted.contains("2026"))
        #expect(!formatted.contains(":"))
    }

    @Test("shortDate degrades to empty string on unparseable input, never crashes")
    func shortDateInvalidInput() {
        #expect(GalleryFormatting.shortDate("not-a-date").isEmpty)
    }

    private static func makeEntry(pieceNumber: Int, title: String?) -> GalleryEntry {
        GalleryEntry(
            id: "piece_\(pieceNumber)",
            createdAt: "2026-09-25T14:30:00.000Z",
            pieceNumber: pieceNumber,
            strokeCount: 3,
            width: 800,
            height: 600,
            drawingStyle: .paint,
            title: title,
            thumbnailToken: "piece_\(pieceNumber)"
        )
    }
}
