import Foundation
import MonetProtocol

/// Pacing constants for `buildRevealSchedule`/`buildRevealPlan`
/// (program-painting spec §4.3, `DEFAULT_REVEAL_PACING`). A pure value —
/// same manifest + pacing always produces the same schedule, so it's safe
/// to compute once when a manifest loads and reuse for the whole playback.
public struct RevealPacing: Equatable, Sendable {
    /// Nominal ms per stroke op.
    public var strokeOpMs: Double
    /// Nominal ms per area op.
    public var areaOpMs: Double
    /// A single keyframe is compressed to at most this.
    public var maxKeyframeMs: Double
    /// The whole version is compressed to at most this.
    public var maxVersionMs: Double

    public init(strokeOpMs: Double = 12, areaOpMs: Double = 250, maxKeyframeMs: Double = 6000, maxVersionMs: Double = 45000) {
        self.strokeOpMs = strokeOpMs
        self.areaOpMs = areaOpMs
        self.maxKeyframeMs = maxKeyframeMs
        self.maxVersionMs = maxVersionMs
    }

    public static let `default` = RevealPacing()
}

/// One keyframe's slice of a `RevealSchedule` — absolute times (ms since
/// version-playback start) bracketing its ops, plus each of its own ops'
/// absolute end time for `revealProgressAt`'s binary search.
public struct RevealScheduleKeyframe: Equatable, Sendable {
    public var label: String
    public var image: String
    public var startMs: Double
    public var endMs: Double
    /// One entry per op in this keyframe, ascending, absolute ms.
    public var opEndMs: [Double]
}

/// The pure, precomputed timing for one version's whole reveal
/// (program-painting spec §4.3, `buildRevealSchedule`'s result).
public struct RevealSchedule: Equatable, Sendable {
    public var totalMs: Double
    public var keyframes: [RevealScheduleKeyframe]
}

/// What's on screen right now for a given elapsed time — the stateless
/// counterpart to `advanceRevealPlan`'s stateful cursor (program-painting
/// spec §4.3, `revealProgressAt`). Treat this as the ground truth for "what
/// should be on screen at time t"; `advanceRevealPlan`'s cursor must never
/// disagree with it (spec §8 test 7).
public enum RevealProgress: Equatable, Sendable {
    case done
    case playing(keyframe: Int, opsDone: Int, active: RevealActiveOp?)
}

/// The op currently mid-reveal within the active keyframe, if any —
/// `nil` when the keyframe boundary itself (not an op) is what's pending
/// (e.g. an empty keyframe waiting to settle).
public struct RevealActiveOp: Equatable, Sendable {
    public var index: Int
    public var progress: Double
}

private func nominalOpMs(_ op: RevealOp, _ pacing: RevealPacing) -> Double {
    switch op {
    case .stroke: pacing.strokeOpMs
    case .area: pacing.areaOpMs
    }
}

/// Two-stage compression: each keyframe is capped at `pacing.maxKeyframeMs`
/// nominal duration, then, if the whole version would still exceed
/// `pacing.maxVersionMs` even after per-keyframe capping, one additional
/// scalar is applied uniformly across every keyframe (program-painting spec
/// §4.3, steps 1-6).
public func buildRevealSchedule(_ manifest: RevealManifest, pacing: RevealPacing = .default) -> RevealSchedule {
    let nominalPerKeyframe = manifest.keyframes.map { kf in kf.ops.reduce(0) { $0 + nominalOpMs($1, pacing) } }
    let cappedPerKeyframe = nominalPerKeyframe.map { min($0, pacing.maxKeyframeMs) }
    let cappedTotal = cappedPerKeyframe.reduce(0, +)
    let versionScale = cappedTotal > pacing.maxVersionMs ? pacing.maxVersionMs / cappedTotal : 1

    var t: Double = 0
    var keyframes: [RevealScheduleKeyframe] = []
    keyframes.reserveCapacity(manifest.keyframes.count)
    for (index, kf) in manifest.keyframes.enumerated() {
        let nominal = nominalPerKeyframe[index]
        let capped = cappedPerKeyframe[index]
        let scale = nominal > 0 ? (capped / nominal) * versionScale : 0
        let startMs = t
        var opEndMs: [Double] = []
        opEndMs.reserveCapacity(kf.ops.count)
        for op in kf.ops {
            t += nominalOpMs(op, pacing) * scale
            opEndMs.append(t)
        }
        keyframes.append(RevealScheduleKeyframe(label: kf.label, image: kf.image, startMs: startMs, endMs: t, opEndMs: opEndMs))
    }
    return RevealSchedule(totalMs: t, keyframes: keyframes)
}

/// Binary search: count of entries `<= value` in an ascending array.
private func countAtOrBefore(_ sortedAscending: [Double], _ value: Double) -> Int {
    var lo = 0
    var hi = sortedAscending.count
    while lo < hi {
        let mid = (lo + hi) / 2
        if sortedAscending[mid] <= value {
            lo = mid + 1
        } else {
            hi = mid
        }
    }
    return lo
}

/// Stateless "what should be shown right now" query (program-painting spec
/// §4.3). `opsDone` is a **local** (within-keyframe) op count.
public func revealProgressAt(_ schedule: RevealSchedule, _ elapsedMs: Double) -> RevealProgress {
    guard elapsedMs < schedule.totalMs else { return .done }
    guard let kfIndex = schedule.keyframes.firstIndex(where: { elapsedMs < $0.endMs }) else { return .done }
    let kf = schedule.keyframes[kfIndex]
    let opsDone = countAtOrBefore(kf.opEndMs, elapsedMs)
    var active: RevealActiveOp?
    if opsDone < kf.opEndMs.count {
        let start = opsDone > 0 ? kf.opEndMs[opsDone - 1] : kf.startMs
        let end = kf.opEndMs[opsDone]
        let duration = end - start
        let progress = duration > 0 ? min(max((elapsedMs - start) / duration, 0), 1) : 0
        active = RevealActiveOp(index: opsDone, progress: progress)
    }
    return .playing(keyframe: kfIndex, opsDone: opsDone, active: active)
}

// MARK: - Flattened per-frame plan (`advanceRevealPlan`'s input)

public enum RevealOpKind: Int, Equatable, Sendable {
    case stroke = 0
    case area = 1
}

/// One keyframe's slice of a `RevealPlan`, indexed into the plan's flattened
/// global op arrays (program-painting spec §4.4).
public struct RevealPlanKeyframe: Equatable, Sendable {
    public var label: String
    public var image: String
    /// Global op index, inclusive.
    public var opStart: Int
    /// Global op index, exclusive. `opStart == opEnd` for a zero-op
    /// keyframe.
    public var opEnd: Int
    public var startMs: Double
    public var endMs: Double
}

/// Every animation frame touches only primitives from this flattened,
/// precomputed structure — no object allocation, no re-walking earlier
/// keyframes (program-painting spec §4.4). Build once per version via
/// `buildRevealPlan`, then drive with repeated `advanceRevealPlan` calls.
public struct RevealPlan: Equatable, Sendable {
    public var width: Int
    public var height: Int
    public var totalMs: Double
    public var keyframes: [RevealPlanKeyframe]
    /// One entry per global op.
    public var opKind: [RevealOpKind]
    /// One entry per global op, ascending, absolute ms.
    public var opEndMs: [Double]
    /// `opDataStart[i]..<opDataStart[i+1]` indexes into `opData` for op
    /// `i`. Length is `opKind.count + 1` (sentinel end).
    public var opDataStart: [Int]
    /// Stroke op: `[width, x0,y0, x1,y1, ...]`; area op: `[x0,y0,x1,y1]` —
    /// tag stripped.
    public var opData: [Double]
}

/// Flattens a `RevealManifest`'s ops into global indices and reuses
/// `buildRevealSchedule` for timing verbatim (never reimplements it), so a
/// `RevealPlan`'s timing can never drift from the shared schedule (spec §8
/// test 3).
public func buildRevealPlan(_ manifest: RevealManifest, pacing: RevealPacing = .default) -> RevealPlan {
    let schedule = buildRevealSchedule(manifest, pacing: pacing)
    var keyframes: [RevealPlanKeyframe] = []
    keyframes.reserveCapacity(manifest.keyframes.count)
    var opKind: [RevealOpKind] = []
    var opEndMs: [Double] = []
    var opDataStart: [Int] = [0]
    var opData: [Double] = []

    for (index, kf) in manifest.keyframes.enumerated() {
        let scheduleKf = schedule.keyframes[index]
        let opStart = opKind.count
        for (opIndex, op) in kf.ops.enumerated() {
            switch op {
            case let .stroke(width, points):
                opKind.append(.stroke)
                opData.append(width)
                for point in points {
                    opData.append(point.x)
                    opData.append(point.y)
                }
            case let .area(x0, y0, x1, y1):
                opKind.append(.area)
                opData.append(contentsOf: [x0, y0, x1, y1])
            }
            opDataStart.append(opData.count)
            opEndMs.append(scheduleKf.opEndMs[opIndex])
        }
        keyframes.append(RevealPlanKeyframe(
            label: kf.label,
            image: kf.image,
            opStart: opStart,
            opEnd: opKind.count,
            startMs: scheduleKf.startMs,
            endMs: scheduleKf.endMs
        ))
    }

    return RevealPlan(
        width: manifest.width,
        height: manifest.height,
        totalMs: schedule.totalMs,
        keyframes: keyframes,
        opKind: opKind,
        opEndMs: opEndMs,
        opDataStart: opDataStart,
        opData: opData
    )
}

/// The cursor `advanceRevealPlan` mutates in place, one per in-progress
/// reveal. Reset to `RevealCursor()` whenever a new version starts playing.
public struct RevealCursor: Equatable, Sendable {
    public var kf: Int
    public var op: Int

    public init(kf: Int = 0, op: Int = 0) {
        self.kf = kf
        self.op = op
    }
}

/// The three drawing primitives every platform reveal layer must implement
/// (program-painting spec §4.4-4.5). A class-based protocol so a test (or a
/// real drawing layer) can record/act on calls without `inout` plumbing.
public protocol RevealSink: AnyObject {
    /// Ops `[from, to)` of keyframe `kf` are now fully revealed.
    func revealOps(kf: Int, from: Int, to: Int)
    /// Draw keyframe `kf`'s image in **full** — not just the accumulated
    /// revealed regions. Load-bearing for correctness (erases seam/rounding
    /// error from incremental clip draws so the next keyframe reveals over
    /// a pixel-exact base), never skip this as an "optimization".
    func settleKeyframe(_ kf: Int)
    /// Partial top-to-bottom wipe preview of an in-flight area op.
    /// Visual-only — never counts as revealed; `cursor.op` does not advance
    /// past this op until its `opEndMs` passes.
    func wipeArea(kf: Int, op: Int, progress: Double)
}

/// Steps `cursor` forward to `elapsedMs` (wall-clock ms since this version
/// started playing — the **same** monotonically increasing value every
/// call, not a per-frame delta), emitting only newly-revealed work to
/// `sink`. Returns `true` once the whole version is fully revealed
/// (program-painting spec §4.4).
///
/// Per-frame cost is proportional only to ops newly revealed since the last
/// call, never to total ops so far — a single call can walk and settle
/// multiple keyframes at once (e.g. after a stall), which is by design, not
/// a bug to special-case away.
@discardableResult
public func advanceRevealPlan(_ plan: RevealPlan, cursor: inout RevealCursor, elapsedMs: Double, sink: RevealSink) -> Bool {
    let nOps = plan.opEndMs.count
    let done = elapsedMs >= plan.totalMs
    var target: Int
    if done {
        target = nOps
    } else {
        // Resume from `cursor.op`, not 0: `elapsedMs` is monotonically
        // increasing and `cursor.op` only moves forward, so the target can
        // never regress. Starting from 0 every call would rescan every
        // already-revealed op each frame (O(ops revealed so far) instead of
        // O(newly revealed) bookkeeping), matching the TS reference
        // (app/src/renderers/revealPlan.ts).
        target = cursor.op
        while target < nOps, plan.opEndMs[target] <= elapsedMs {
            target += 1
        }
    }

    while cursor.kf < plan.keyframes.count {
        let kf = plan.keyframes[cursor.kf]
        let upto = min(target, kf.opEnd)
        if upto > cursor.op {
            sink.revealOps(kf: cursor.kf, from: cursor.op, to: upto)
            cursor.op = upto
        }
        if cursor.op < kf.opEnd { break }
        if !done, elapsedMs < kf.endMs { break }
        sink.settleKeyframe(cursor.kf)
        cursor.kf += 1
    }

    guard cursor.kf < plan.keyframes.count else { return true }

    let kf = plan.keyframes[cursor.kf]
    let op = cursor.op
    if op < kf.opEnd, plan.opKind[op] == .area {
        let start = op > kf.opStart ? plan.opEndMs[op - 1] : kf.startMs
        let duration = plan.opEndMs[op] - start
        let progress = duration > 0 ? min(max((elapsedMs - start) / duration, 0), 1) : 0
        if progress > 0 {
            sink.wipeArea(kf: cursor.kf, op: op, progress: progress)
        }
    }
    return false
}

// MARK: - Gallery / capability-URL joining (program-painting spec §2.1, §8 tests 10-11)

public enum PaintingAssetURL {
    /// Joins an API-relative `path` onto `apiBase` (program-painting spec
    /// §2.1, `apiAssetUrl`). A trailing slash on `apiBase` is stripped
    /// before joining; a `path` that's already absolute (carries its own
    /// scheme, e.g. a CDN URL) passes through unchanged.
    public static func apiAssetUrl(_ apiBase: String, _ path: String) -> String {
        if path.contains("://") { return path }
        let base = apiBase.hasSuffix("/") ? String(apiBase.dropLast()) : apiBase
        return base + path
    }

    /// A painting version's `asset_base` + filename, resolved against the
    /// API base (spec §2.1, `paintingAssetUrl`). `asset_base` always ends
    /// in `/`.
    public static func paintingAssetUrl(apiBase: String, ref: PaintingVersionRef, file: String) -> String {
        apiAssetUrl(apiBase, ref.assetBase + file)
    }

    /// Only resolves for a raster piece with a non-nil `image_url` (spec §8
    /// test 11, `galleryRasterImageUrl`) — `nil` for `.strokes` regardless
    /// of `imageURL`, and for `.raster` with a `nil` `imageURL`.
    public static func galleryRasterImageUrl(apiBase: String, format: GalleryPieceFormat, imageURL: String?) -> String? {
        guard format == .raster, let imageURL else { return nil }
        return apiAssetUrl(apiBase, imageURL)
    }
}
