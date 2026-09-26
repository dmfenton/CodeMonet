import Foundation
import MonetProtocol
import MonetStudio

/// The Gallery's style filter chips (from each entry's `drawing_style`).
enum GalleryFilter: String, CaseIterable, Identifiable {
    case all, paint, plotter

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all: "All"
        case .paint: "Paint"
        case .plotter: "Plotter"
        }
    }

    func includes(_ entry: GalleryEntry) -> Bool {
        switch self {
        case .all: true
        case .paint: entry.drawingStyle == .paint
        case .plotter: entry.drawingStyle == .plotter
        }
    }
}

/// Pure formatting helpers for the Gallery and its piece detail, factored
/// out of the views so they're unit-testable.
enum GalleryFormatting {
    /// Newest piece first.
    static func newestFirst(_ entries: [GalleryEntry]) -> [GalleryEntry] {
        entries.sorted { $0.pieceNumber > $1.pieceNumber }
    }

    /// The shared title fallback (list entries carry no prompt).
    static func title(for entry: GalleryEntry) -> String {
        PieceTitle.resolve(title: entry.title, prompt: nil, pieceNumber: entry.pieceNumber)
    }

    /// "Sep 25" — no year, no time.
    static func shortDate(_ isoString: String) -> String {
        guard let date = parseISO8601(isoString) else { return "" }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }

    /// "Sep 25, 2026".
    static func longDate(_ isoString: String) -> String {
        guard let date = parseISO8601(isoString) else { return "" }
        return date.formatted(.dateTime.month(.abbreviated).day().year())
    }

    /// "38 pieces · since March" (or "since Mar 2025" for an earlier year).
    static func summaryLine(for entries: [GalleryEntry], now: Date = Date()) -> String {
        let count = "\(entries.count) piece\(entries.count == 1 ? "" : "s")"
        let earliest = entries.compactMap { parseISO8601($0.createdAt) }.min()
        guard let earliest else { return count }
        let calendar = Calendar.current
        let since = calendar.component(.year, from: earliest) == calendar.component(.year, from: now)
            ? earliest.formatted(.dateTime.month(.wide))
            : earliest.formatted(.dateTime.month(.abbreviated).year())
        return "\(count) · since \(since)"
    }

    static func styleLabel(_ style: DrawingStyleType) -> String {
        style == .paint ? "paint" : "plotter"
    }

    /// The detail's meta line: "Sep 24, 2026 · paint · 4 versions · 1,284
    /// strokes". Versions and strokes appear only when known and non-zero.
    static func detailMetaLine(createdAt: String, style: DrawingStyleType, versionCount: Int, strokeCount: Int?) -> String {
        var parts = [longDate(createdAt), styleLabel(style)].filter { !$0.isEmpty }
        if versionCount > 0 { parts.append("\(versionCount) version\(versionCount == 1 ? "" : "s")") }
        if let strokeCount, strokeCount > 0 {
            parts.append("\(strokeCount.formatted()) stroke\(strokeCount == 1 ? "" : "s")")
        }
        return parts.joined(separator: " · ")
    }

    private static func parseISO8601(_ string: String) -> Date? {
        let withFractional = ISO8601DateFormatter()
        withFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = withFractional.date(from: string) { return date }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: string)
    }
}
