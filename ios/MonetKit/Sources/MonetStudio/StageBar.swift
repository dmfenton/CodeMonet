import MonetProtocol

/// One pass of a painting version, as the stage bar sees it: its
/// `cv.stage(...)` label and how much work it holds (the hand time of its
/// strokes in the performance, or `1` when only the labels are known).
public struct StageSpec: Equatable, Sendable {
    public var label: String
    public var weight: Double

    public init(label: String, weight: Double = 1) {
        self.label = label
        self.weight = weight
    }

    /// Labels only (a version's `stages` list): equal widths.
    public static func labels(_ labels: [String]) -> [StageSpec] {
        labels.map { StageSpec(label: $0) }
    }
}

/// One stage of a painting version, as drawn in the Studio's stage bar.
public struct StageSegment: Equatable, Sendable, Identifiable {
    public enum Progress: Equatable, Sendable {
        case done
        case current
        case pending
    }

    /// Index of the segment's first `StageSpec`.
    public var id: Int
    public var label: String
    /// Summed `StageSpec.weight` of the merged specs.
    public var weight: Double
    /// Share of the bar's width, `0...1`; all segments sum to 1.
    public var fraction: Double
    public var progress: Progress

    public init(id: Int, label: String, weight: Double, fraction: Double, progress: Progress) {
        self.id = id
        self.label = label
        self.weight = weight
        self.fraction = fraction
        self.progress = progress
    }
}

/// Stage bar model: one segment per stage (consecutive specs with the same
/// label merged), width proportional to its weight with a floor so small
/// stages stay visible.
public enum StageBar {
    public static let defaultMinimumFraction = 0.08

    /// - Parameter active: index of the spec being painted right now, or
    ///   `nil` when the version is fully shown.
    public static func segments(
        stages: [StageSpec],
        active: Int?,
        minimumFraction: Double = defaultMinimumFraction
    ) -> [StageSegment] {
        var groups: [(first: Int, last: Int, label: String, weight: Double)] = []
        for (index, stage) in stages.enumerated() {
            if let lastGroup = groups.last, lastGroup.label == stage.label {
                groups[groups.count - 1] = (lastGroup.first, index, lastGroup.label, lastGroup.weight + max(stage.weight, 0))
            } else {
                groups.append((index, index, stage.label, max(stage.weight, 0)))
            }
        }
        let fractions = flooredFractions(groups.map(\.weight), minimum: minimumFraction)
        return groups.enumerated().map { offset, group in
            StageSegment(
                id: group.first,
                label: group.label,
                weight: group.weight,
                fraction: fractions[offset],
                progress: progress(first: group.first, last: group.last, revealing: active)
            )
        }
    }

    private static func progress(first: Int, last: Int, revealing: Int?) -> StageSegment.Progress {
        guard let revealing else { return .done }
        if revealing > last { return .done }
        if revealing >= first { return .current }
        return .pending
    }

    /// Proportional shares where any share under `minimum` is raised to it
    /// and the rest shrink proportionally to compensate (so every share is
    /// `>= minimum` and they still sum to 1). Equal shares when the weights
    /// are all zero or the floor can't be honored for every segment.
    static func flooredFractions(_ weights: [Double], minimum: Double) -> [Double] {
        let count = weights.count
        guard count > 0 else { return [] }
        let total = weights.reduce(0, +)
        guard total > 0, minimum * Double(count) < 1 else {
            return Array(repeating: 1 / Double(count), count: count)
        }
        var floored = Set<Int>()
        while true {
            let freeWeight = weights.indices.filter { !floored.contains($0) }.reduce(0) { $0 + weights[$1] }
            let freeShare = 1 - minimum * Double(floored.count)
            let newlyFloored = weights.indices.filter {
                !floored.contains($0) && (freeWeight <= 0 || weights[$0] / freeWeight * freeShare < minimum)
            }
            if newlyFloored.isEmpty {
                return weights.indices.map { floored.contains($0) ? minimum : weights[$0] / freeWeight * freeShare }
            }
            floored.formUnion(newlyFloored)
        }
    }
}

/// Title fallback shared by every screen: title, else the prompt (trimmed
/// to a short line), else "Piece N". Never invents a title.
public enum PieceTitle {
    public static let maxPromptLength = 44

    public static func resolve(title: String?, prompt: String?, pieceNumber: Int) -> String {
        if let title = nonEmpty(title) { return title }
        if let prompt = nonEmpty(prompt) { return truncate(prompt, to: maxPromptLength) }
        return "Piece \(pieceNumber)"
    }

    static func truncate(_ text: String, to limit: Int) -> String {
        guard text.count > limit else { return text }
        let prefix = String(text.prefix(limit))
        let cut = prefix.lastIndex(of: " ").map { String(prefix[..<$0]) } ?? prefix
        return cut.trimmingCharacters(in: .whitespacesAndNewlines.union(.punctuationCharacters)) + "…"
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else { return nil }
        return trimmed
    }
}
