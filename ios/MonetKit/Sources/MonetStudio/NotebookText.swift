import Foundation
import MonetProtocol

/// Display text for notebook entries — shared rules, kept pure so every
/// client words them the same way.
public enum NotebookText {
    /// One domain tool line, e.g. "paint v4 · 318 strokes · 2.1s",
    /// "looked at the canvas", "named it “Dusk”". `strokes` is shown only
    /// for a paint call that produced a version.
    public static func toolLine(_ call: NotebookToolCall, strokes: Int?) -> String {
        if call.failed { return "\(shortName(call.toolName)) · failed" }
        switch call.toolName {
        case "paint":
            return paintLine(call, strokes: strokes)
        case "view_canvas":
            return call.inProgress ? "looking at the canvas…" : "looked at the canvas"
        case "imagine":
            return call.inProgress ? "imagining a reference…" : "imagined a reference"
        case "sign_canvas":
            return call.inProgress ? "signing the canvas…" : "signed the canvas"
        case "mark_piece_done":
            return call.inProgress ? "marking the piece done…" : "marked the piece done"
        case "name_piece":
            if call.inProgress { return "naming it…" }
            return call.title.map { "named it “\($0)”" } ?? "named it"
        case "critique_canvas":
            return call.inProgress ? "critiquing…" : "critiqued"
        case "draw_paths":
            return call.inProgress ? "drawing paths…" : "drew paths"
        case "generate_svg":
            return call.inProgress ? "generating an svg…" : "generated an svg"
        default:
            return call.inProgress ? "\(shortName(call.toolName))…" : shortName(call.toolName)
        }
    }

    /// A collapsed housekeeping run: "write · edit · bash".
    public static func housekeepingLine(_ names: [String]) -> String {
        names.joined(separator: " · ")
    }

    /// "0.4s", "12.0s", "1m 04s".
    public static func duration(milliseconds: Double) -> String {
        let seconds = max(0, milliseconds) / 1000
        if seconds < 60 { return String(format: "%.1fs", seconds) }
        let whole = Int(seconds.rounded())
        return String(format: "%dm %02ds", whole / 60, whole % 60)
    }

    private static func paintLine(_ call: NotebookToolCall, strokes: Int?) -> String {
        if call.inProgress {
            return call.producedVersion.map { "paint v\($0)…" } ?? "paint…"
        }
        var head = "paint"
        if let version = call.producedVersion { head += " v\(version)" }
        var parts = [head]
        if call.producedVersion != nil, let strokes {
            parts.append("\(strokes.formatted()) stroke\(strokes == 1 ? "" : "s")")
        }
        if let durationMs = call.durationMs { parts.append(duration(milliseconds: durationMs)) }
        return parts.joined(separator: " · ")
    }

    private static func shortName(_ toolName: String?) -> String {
        (toolName ?? "tool").replacingOccurrences(of: "_", with: " ").lowercased()
    }
}

/// A `critique_canvas` result, cleaned for display: the verdict pulled out
/// of the text, the "FINDINGS:" header and trailing "FINISH GATE:"
/// instructions dropped, and the body split into paragraphs and bullets
/// (inline markdown is left for the renderer).
public struct CritiqueSummary: Equatable, Sendable {
    public enum Verdict: Equatable, Sendable {
        case pass, fail
    }

    public enum Line: Equatable, Sendable {
        case paragraph(String)
        /// A "- " / "* " list item; `level` counts leading indentation.
        case bullet(String, level: Int)
    }

    public var verdict: Verdict?
    public var lines: [Line]

    /// "critique · pass", "critique · fail", or "critique".
    public var label: String {
        switch verdict {
        case .pass: "critique · pass"
        case .fail: "critique · fail"
        case nil: "critique"
        }
    }

    public init(verdict: Verdict?, lines: [Line]) {
        self.verdict = verdict
        self.lines = lines
    }

    public init(parsing text: String) {
        var verdict: Verdict?
        var kept: [String] = []
        for raw in text.components(separatedBy: .newlines) {
            let bare = Self.stripEmphasis(raw.trimmingCharacters(in: .whitespaces))
            let upper = bare.uppercased()
            if upper.hasPrefix("FINISH GATE") { break }
            if upper.hasPrefix("VERDICT") {
                if upper.contains("PASS") { verdict = .pass } else if upper.contains("FAIL") { verdict = .fail }
                continue
            }
            if kept.allSatisfy({ $0.trimmingCharacters(in: .whitespaces).isEmpty }), upper.hasPrefix("FINDINGS") {
                let rest = bare.drop(while: { $0 != ":" }).dropFirst().trimmingCharacters(in: .whitespaces)
                if !rest.isEmpty { kept.append(rest) }
                continue
            }
            kept.append(raw)
        }
        self.verdict = verdict
        lines = Self.lines(kept)
    }

    /// Paragraphs (consecutive non-bullet lines joined) and bullets; blank
    /// lines separate paragraphs and are otherwise dropped.
    private static func lines(_ raw: [String]) -> [Line] {
        var result: [Line] = []
        var paragraph: [String] = []
        func flush() {
            if !paragraph.isEmpty { result.append(.paragraph(paragraph.joined(separator: " "))) }
            paragraph = []
        }
        for line in raw {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty {
                flush()
            } else if trimmed.hasPrefix("- ") || trimmed.hasPrefix("* ") || trimmed.hasPrefix("• ") {
                flush()
                let indent = line.prefix(while: { $0 == " " || $0 == "\t" }).count
                result.append(.bullet(String(trimmed.dropFirst(2)), level: indent >= 2 ? 1 : 0))
            } else if paragraph.isEmpty, line.first == " " || line.first == "\t",
                      case let .bullet(text, level)? = result.last {
                // An indented continuation of the bullet above.
                result[result.count - 1] = .bullet(text + " " + trimmed, level: level)
            } else {
                paragraph.append(trimmed)
            }
        }
        flush()
        return result
    }

    /// "**VERDICT:** FAIL" -> "VERDICT: FAIL" for header matching only.
    private static func stripEmphasis(_ line: String) -> String {
        line.replacingOccurrences(of: "**", with: "").replacingOccurrences(of: "__", with: "")
            .trimmingCharacters(in: CharacterSet(charactersIn: "#").union(.whitespaces))
    }
}

public extension StageBar {
    /// Whether every segment can show its full label: each segment's width
    /// (`totalWidth` minus inter-segment spacing, times its fraction) must fit
    /// `label.count * characterWidth` (labels are monospaced).
    static func labelsFit(_ segments: [StageSegment], totalWidth: Double, spacing: Double, characterWidth: Double) -> Bool {
        let available = totalWidth - spacing * Double(max(segments.count - 1, 0))
        return segments.allSatisfy { available * $0.fraction >= Double($0.label.count) * characterWidth }
    }

    /// The single caption shown when labels don't fit: "stage 4 of 8 ·
    /// harbor" while revealing, "8 stages · final touches" when done.
    static func caption(_ segments: [StageSegment]) -> String {
        guard let last = segments.last else { return "" }
        if let current = segments.firstIndex(where: { $0.progress == .current }) {
            return "stage \(current + 1) of \(segments.count) · \(segments[current].label)"
        }
        return "\(segments.count) stage\(segments.count == 1 ? "" : "s") · \(last.label)"
    }
}
