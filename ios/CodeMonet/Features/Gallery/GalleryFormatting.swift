import Foundation
import MonetProtocol

/// Pure formatting helpers for the Gallery grid (ux spec §8), factored out
/// of the view so date/meta-line logic is unit-testable without a live
/// `AppEnvironment`.
enum GalleryFormatting {
    /// `created_at` (ISO 8601, e.g. from `GalleryEntry.createdAt`) -> a
    /// locale-aware short date with no year/time (RN's
    /// `date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })`,
    /// e.g. "Sep 25").
    static func shortDate(_ isoString: String) -> String {
        guard let date = parseISO8601(isoString) else { return "" }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }

    /// Cell title: the piece's name if the agent named it, else `#N`.
    static func title(for entry: GalleryEntry) -> String {
        entry.title ?? "#\(entry.pieceNumber)"
    }

    /// Meta line: `#N · <date>` when a title exists (to avoid repeating the
    /// number in the title above it), else just `<date>`.
    static func metaLine(for entry: GalleryEntry) -> String {
        let date = shortDate(entry.createdAt)
        guard entry.title != nil else { return date }
        return "#\(entry.pieceNumber) · \(date)"
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
