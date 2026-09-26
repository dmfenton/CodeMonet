import MonetProtocol

/// One stage of a painting version, as drawn in the Studio's stage bar.
public struct StageSegment: Equatable, Sendable, Identifiable {
    public enum Progress: Equatable, Sendable {
        case done
        case current
        case pending
    }

    /// Index of the segment's first keyframe in `reveal.json`.
    public var id: Int
    public var label: String
    public var opCount: Int
    /// Share of the bar's width, `0...1`; all segments sum to 1.
    public var fraction: Double
    public var progress: Progress

    public init(id: Int, label: String, opCount: Int, fraction: Double, progress: Progress) {
        self.id = id
        self.label = label
        self.opCount = opCount
        self.fraction = fraction
        self.progress = progress
    }
}

/// Stage bar model: one segment per `reveal.json` keyframe (consecutive
/// keyframes with the same label merged), width proportional to its op
/// count with a floor so small stages stay visible.
public enum StageBar {
    public static let defaultMinimumFraction = 0.08

    /// - Parameter revealingKeyframe: the keyframe index currently being
    ///   revealed, or `nil` when the version is fully shown.
    public static func segments(
        manifest: RevealManifest,
        revealingKeyframe: Int?,
        minimumFraction: Double = defaultMinimumFraction
    ) -> [StageSegment] {
        var groups: [(first: Int, last: Int, label: String, ops: Int)] = []
        for (index, keyframe) in manifest.keyframes.enumerated() {
            if let lastGroup = groups.last, lastGroup.label == keyframe.label {
                groups[groups.count - 1] = (lastGroup.first, index, lastGroup.label, lastGroup.ops + keyframe.ops.count)
            } else {
                groups.append((index, index, keyframe.label, keyframe.ops.count))
            }
        }
        let fractions = flooredFractions(groups.map { Double($0.ops) }, minimum: minimumFraction)
        return groups.enumerated().map { offset, group in
            StageSegment(
                id: group.first,
                label: group.label,
                opCount: group.ops,
                fraction: fractions[offset],
                progress: progress(first: group.first, last: group.last, revealing: revealingKeyframe)
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
