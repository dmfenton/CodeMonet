@testable import CodeMonet
import Foundation
import MonetProtocol
import Testing

@Suite("GalleryFormatting")
struct GalleryFormattingTests {
    @Test("title falls back to 'Piece N' when untitled")
    func titleFallback() {
        #expect(GalleryFormatting.title(for: Self.makeEntry(pieceNumber: 7, title: nil)) == "Piece 7")
        #expect(GalleryFormatting.title(for: Self.makeEntry(pieceNumber: 7, title: "Sunset")) == "Sunset")
    }

    @Test("newestFirst orders by piece number, descending")
    func newestFirst() {
        let entries = [3, 9, 5].map { Self.makeEntry(pieceNumber: $0, title: nil) }
        #expect(GalleryFormatting.newestFirst(entries).map(\.pieceNumber) == [9, 5, 3])
    }

    @Test("filters select by drawing style")
    func filters() {
        let paint = Self.makeEntry(pieceNumber: 1, title: nil, style: .paint)
        let plotter = Self.makeEntry(pieceNumber: 2, title: nil, style: .plotter)
        #expect(GalleryFilter.all.includes(paint) && GalleryFilter.all.includes(plotter))
        #expect(GalleryFilter.paint.includes(paint) && !GalleryFilter.paint.includes(plotter))
        #expect(GalleryFilter.plotter.includes(plotter) && !GalleryFilter.plotter.includes(paint))
    }

    @Test("summary line counts pieces and names the earliest month")
    func summaryLine() throws {
        let entries = [
            Self.makeEntry(pieceNumber: 1, title: nil, createdAt: "2026-03-02T12:00:00Z"),
            Self.makeEntry(pieceNumber: 2, title: nil, createdAt: "2026-09-25T12:00:00Z"),
        ]
        let now = try #require(ISO8601DateFormatter().date(from: "2026-09-26T12:00:00Z"))
        let line = GalleryFormatting.summaryLine(for: entries, now: now)
        #expect(line.hasPrefix("2 pieces · since "))
        #expect(!line.contains("2026"))
        #expect(GalleryFormatting.summaryLine(for: [], now: now) == "0 pieces")
        let lastYear = try #require(ISO8601DateFormatter().date(from: "2027-02-01T12:00:00Z"))
        #expect(GalleryFormatting.summaryLine(for: entries, now: lastYear).contains("2026"))
    }

    @Test("detail meta line omits unknown versions and zero strokes")
    func detailMetaLine() {
        let full = GalleryFormatting.detailMetaLine(
            createdAt: "2026-09-24T12:00:00Z", style: .paint, versionCount: 4, strokeCount: 1284
        )
        #expect(full.hasSuffix(" · paint · 4 versions · 1,284 strokes"))
        let bare = GalleryFormatting.detailMetaLine(createdAt: "2026-09-24T12:00:00Z", style: .plotter, versionCount: 0, strokeCount: 0)
        #expect(bare.hasSuffix(" · plotter"))
    }

    @Test("shortDate has no year and no time, matching the RN 'Sep 25' format")
    func shortDateFormat() {
        let formatted = GalleryFormatting.shortDate("2026-09-25T14:30:00.000Z")
        #expect(!formatted.isEmpty)
        #expect(!formatted.contains("2026"))
        #expect(!formatted.contains(":"))
    }

    @Test("dates degrade to empty strings on unparseable input, never crash")
    func invalidDates() {
        #expect(GalleryFormatting.shortDate("not-a-date").isEmpty)
        #expect(GalleryFormatting.longDate("not-a-date").isEmpty)
    }

    private static func makeEntry(
        pieceNumber: Int,
        title: String?,
        style: DrawingStyleType = .paint,
        createdAt: String = "2026-09-25T14:30:00.000Z"
    ) -> GalleryEntry {
        GalleryEntry(
            id: "piece_\(pieceNumber)",
            createdAt: createdAt,
            pieceNumber: pieceNumber,
            strokeCount: 3,
            width: 800,
            height: 600,
            drawingStyle: style,
            title: title,
            thumbnailToken: "piece_\(pieceNumber)"
        )
    }
}
