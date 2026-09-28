import CoreGraphics
import Foundation

/// A chunk's atlases, decoded: the color atlas as RGBA and the order atlas
/// as one byte per 4x4 block (its red channel).
public struct PerformanceAtlas: Sendable {
    public var color: RGBAPixels
    public var order: [UInt8]
    public var orderSize: PixelSize

    public init(color: RGBAPixels, order: [UInt8], orderSize: PixelSize) {
        self.color = color
        self.order = order
        self.orderSize = orderSize
    }

    /// Decodes a chunk frame's color (lossy WebP) and order (lossless WebP)
    /// parts via ImageIO. Pure and `Sendable`: run it off the main thread.
    public static func decode(color: Data, order: Data) throws -> PerformanceAtlas {
        let colorPixels = try PaintingImageDecoder.decodeRGBA(color)
        let orderPixels = try PaintingImageDecoder.decodeRGBA(order)
        var values = [UInt8](repeating: 0, count: orderPixels.width * orderPixels.height)
        orderPixels.bytes.withUnsafeBufferPointer { rgba in
            for index in values.indices { values[index] = rgba[index * 4] }
        }
        return PerformanceAtlas(
            color: colorPixels,
            order: values,
            orderSize: PixelSize(width: orderPixels.width, height: orderPixels.height)
        )
    }
}

/// One `cv.stage(...)` pass of a performance, for the stage bar:
/// consecutive chunks with the same label merged; `handMs` is the hand time
/// of its strokes.
public struct PerformanceStage: Equatable, Sendable {
    public var label: String
    public var handMs: Double

    public init(label: String, handMs: Double) {
        self.label = label
        self.handMs = handMs
    }
}

/// Plays a performance stream into a picture buffer (port of
/// `web/src/renderers/PerformancePlayer.tsx`'s playback loop, minus the
/// fetch): frames are ingested in stream order as they arrive, and each
/// `advance(byMs:)` pastes the patches due at the new hand time, in paint
/// order. An in-flight patch pastes the pixels whose 4x4 block's draw order
/// (0 read as 255) is <= `performanceOrderThreshold`; a finished patch is
/// pasted whole (its unchanged pixels hold the current picture, so pasting
/// them is harmless). Playback never passes what has arrived, nor a chunk
/// whose atlases are not decoded yet.
///
/// Atlases are decoded lazily — only the chunk being played and the next
/// `decodeLookahead` — and released once played, so a long complete stream
/// never holds every decoded atlas at once. The caller decodes them off the
/// main thread (`nextChunkToDecode` / `PerformanceAtlas.decode` /
/// `chunkDecoded`).
///
/// Not thread-safe: drive it from one actor (the app's main actor).
public final class PerformancePlayer {
    /// Picture size (header `width` x `height`).
    public let size: PixelSize
    /// The stream is a revision (header `base: "previous"`).
    public let isRevision: Bool
    /// Hand time played so far (ms).
    public private(set) var handMs: Double = 0
    /// The stream is complete (end frame, error frame, or the connection
    /// closed).
    public private(set) var ended = false
    /// The stream ended with an error frame (the program raised).
    public private(set) var failed = false

    /// Chunks decoded ahead of the one playing.
    public static let decodeLookahead = 2

    private var picture: RGBAPixels
    private var dirty = true
    private var endMs: Double?
    private var chunks: [Chunk] = []
    private var entries: [Entry] = []
    /// Every entry before this is fully pasted (or skipped).
    private var cursor = 0

    private struct Entry {
        var patch: PerformancePatch
        var chunk: Int
        var valid: Bool
    }

    private enum AtlasState {
        case pending(color: Data, order: Data)
        case decoding
        case ready(PerformanceAtlas)
        /// Undecodable or already played: its remaining entries are skipped.
        case gone
    }

    private struct Chunk {
        var stage: String
        var claimedColor: PixelSize
        var claimedOrder: PixelSize
        var entries: Range<Int>
        var handMs: Double
        var atlas: AtlasState
    }

    /// `nil` for a header whose picture size is empty or larger than
    /// `RGBAPixels.maxPixelCount` (untrusted program output).
    /// - Parameter base: the picture before the performance (the previous
    ///   version's final), drawn to fill under a revision's stream; a stream
    ///   painted from blank starts white whatever is passed.
    public init?(header: PerformanceMeta, base: CGImage?) {
        guard case let .header(width, height, _, base: streamBase) = header,
              withinPixelBudget(width, height)
        else { return nil }
        size = PixelSize(width: width, height: height)
        isRevision = streamBase == .previous
        picture = RGBAPixels(width: width, height: height)
        if isRevision, let base { picture.draw(base) }
    }

    // MARK: - Ingest

    /// Takes the next frame after the header, in stream order.
    public func ingest(_ frame: PerformanceFrame) {
        guard !ended else { return }
        switch frame.meta {
        case let .chunk(stage, atlasWidth, atlasHeight, _):
            ingestChunk(stage: stage, atlasWidth: atlasWidth, atlasHeight: atlasHeight, frame: frame)
        case let .end(ms):
            endMs = ms.isFinite ? ms : nil
            ended = true
        case .error, .malformed:
            failed = true
            ended = true
        case .header, .unknown:
            break
        }
    }

    /// The connection closed (with or without an end frame): whatever has
    /// arrived is the whole performance.
    public func finishStream() {
        ended = true
    }

    private func ingestChunk(stage: String, atlasWidth: Int, atlasHeight: Int, frame: PerformanceFrame) {
        let k = performanceOrderScale
        // Sizes come from the program's output: checked before any arithmetic on them.
        let plausible = withinPixelBudget(atlasWidth, atlasHeight)
        let claimedColor = PixelSize(width: atlasWidth, height: atlasHeight)
        let claimedOrder = plausible
            ? PixelSize(width: (atlasWidth + k - 1) / k, height: (atlasHeight + k - 1) / k)
            : PixelSize(width: 0, height: 0)
        let index = chunks.count
        let first = entries.count
        var handMs = 0.0
        if plausible {
            for patch in decodePerformancePatches(frame.index)
                where performancePatchFits(patch, picture: size, color: claimedColor, order: claimedOrder) {
                entries.append(Entry(patch: patch, chunk: index, valid: true))
                handMs += max(patch.dur, 0)
            }
        }
        let range = first ..< entries.count
        chunks.append(Chunk(
            stage: stage,
            claimedColor: claimedColor,
            claimedOrder: claimedOrder,
            entries: range,
            handMs: handMs,
            atlas: range.isEmpty ? .gone : .pending(color: frame.color, order: frame.order)
        ))
    }

    // MARK: - Decoding

    /// The next chunk (the one playing or up to `decodeLookahead` after it)
    /// whose atlases need decoding; marks it as decoding. Hand the bytes to
    /// `PerformanceAtlas.decode` and the result to `chunkDecoded`.
    public func nextChunkToDecode() -> (chunk: Int, color: Data, order: Data)? {
        let playing = cursor < entries.count ? entries[cursor].chunk : chunks.count
        var ahead = 0
        var index = playing
        while index < chunks.count, ahead <= Self.decodeLookahead {
            if case let .pending(color, order) = chunks[index].atlas {
                chunks[index].atlas = .decoding
                return (index, color, order)
            }
            if !chunks[index].entries.isEmpty { ahead += 1 }
            index += 1
        }
        return nil
    }

    /// A chunk's decoded atlases (`nil`: undecodable — its patches are
    /// skipped). Patches that don't fit the actual atlas sizes are skipped.
    public func chunkDecoded(_ chunk: Int, atlas: PerformanceAtlas?) {
        guard chunks.indices.contains(chunk), case .decoding = chunks[chunk].atlas else { return }
        guard let atlas else {
            chunks[chunk].atlas = .gone
            return
        }
        let colorSize = PixelSize(width: atlas.color.width, height: atlas.color.height)
        for index in chunks[chunk].entries
            where !performancePatchFits(entries[index].patch, picture: size, color: colorSize, order: atlas.orderSize) {
            entries[index].valid = false
        }
        chunks[chunk].atlas = .ready(atlas)
    }

    // MARK: - Playback

    /// Hand time of everything that has arrived (the end, once known).
    private var arrivedMs: Double {
        let lastEnd = entries.last.map { max($0.patch.end, $0.patch.t) } ?? 0
        guard ended else { return lastEnd }
        return max(endMs ?? 0, lastEnd)
    }

    /// Hand time of the first patch whose atlases aren't decoded yet.
    private var blockedMs: Double? {
        let playing = cursor < entries.count ? entries[cursor].chunk : chunks.count
        for index in playing ..< chunks.count {
            switch chunks[index].atlas {
            case .pending, .decoding:
                return chunks[index].entries.first.map { entries[$0].patch.t }
            case .ready, .gone:
                continue
            }
        }
        return nil
    }

    /// True once the whole stream has arrived and played.
    public var isFinished: Bool {
        ended && cursor >= entries.count && handMs >= arrivedMs
    }

    /// Advances playback by `wallMs` of wall-clock time at `baseRate` hand
    /// ms per ms (sped up by `performancePlaybackRate` when far behind what
    /// has arrived) and pastes what became due. Returns whether the picture
    /// changed since the last `takeImageIfChanged()`.
    @discardableResult
    public func advance(byMs wallMs: Double, baseRate: Double, maxBehindMs: Double = performanceMaxBehindMs) -> Bool {
        let arrived = arrivedMs
        var horizon = arrived
        if let blocked = blockedMs { horizon = min(horizon, blocked) }
        // The stroke in flight (if any) is played legibly unless catching up.
        let flight = cursor < entries.count ? entries[cursor].patch : nil
        let activeDur = flight.flatMap { $0.t <= handMs ? $0.dur : nil }
        let rate = performancePlaybackRate(
            baseRate: max(0, baseRate),
            backlogMs: arrived - handMs,
            maxBehindMs: maxBehindMs,
            activeDurMs: activeDur
        )
        handMs = max(handMs, min(handMs + max(0, wallMs) * rate, horizon))
        pasteDue()
        return dirty
    }

    private func pasteDue() {
        var index = cursor
        while index < entries.count, entries[index].patch.t <= handMs {
            let entry = entries[index]
            var finished = true
            switch chunks[entry.chunk].atlas {
            case let .ready(atlas):
                if entry.valid {
                    let threshold = performanceOrderThreshold(entry.patch, now: handMs)
                    paste(entry.patch, atlas: atlas, threshold: threshold)
                    finished = threshold >= 256
                }
            case .gone:
                break
            case .pending, .decoding:
                // Not decoded yet (the horizon normally stops short of it).
                return
            }
            if finished, index == cursor {
                cursor += 1
                releaseIfPlayed(entry.chunk)
            }
            index += 1
        }
    }

    private func releaseIfPlayed(_ chunk: Int) {
        if cursor >= chunks[chunk].entries.upperBound, case .ready = chunks[chunk].atlas {
            chunks[chunk].atlas = .gone
        }
    }

    /// Copies a patch's pixels whose draw order is <= `threshold` into the picture.
    private func paste(_ p: PerformancePatch, atlas: PerformanceAtlas, threshold: Double) {
        let k = performanceOrderScale
        let pictureWidth = size.width
        let colorWidth = atlas.color.width
        let orderWidth = atlas.orderSize.width
        let full = threshold >= 256
        picture.bytes.withUnsafeMutableBufferPointer { out in
            atlas.color.bytes.withUnsafeBufferPointer { color in
                atlas.order.withUnsafeBufferPointer { order in
                    for row in 0 ..< p.h {
                        let src = ((p.ay + row) * colorWidth + p.ax) * 4
                        let dst = ((p.y + row) * pictureWidth + p.x) * 4
                        if full {
                            out.baseAddress!.advanced(by: dst).update(from: color.baseAddress!.advanced(by: src), count: p.w * 4)
                            continue
                        }
                        let orderRow = ((p.ay + row) / k) * orderWidth
                        for column in 0 ..< p.w {
                            let value = order[orderRow + (p.ax + column) / k]
                            if Double(value == 0 ? 255 : value) > threshold { continue }
                            let s = src + column * 4
                            let d = dst + column * 4
                            out[d] = color[s]
                            out[d + 1] = color[s + 1]
                            out[d + 2] = color[s + 2]
                            out[d + 3] = 255
                        }
                    }
                }
            }
        }
        dirty = true
    }

    // MARK: - Output

    /// The current picture, or `nil` when nothing changed since the last call.
    public func takeImageIfChanged() -> CGImage? {
        guard dirty else { return nil }
        dirty = false
        return picture.makeImage()
    }

    /// The current picture's pixels (tests, final-frame capture).
    public var pixels: RGBAPixels { picture }

    /// The stages that have arrived, in order (consecutive chunks with the
    /// same label merged), and the index of the one playing: the last one
    /// while a live stream waits for more, `nil` once the whole stream has
    /// played.
    public var stages: (stages: [PerformanceStage], active: Int?) {
        var stages: [PerformanceStage] = []
        var active: Int?
        let playing = cursor < entries.count ? entries[cursor].chunk : nil
        for (index, chunk) in chunks.enumerated() {
            if let last = stages.last, last.label == chunk.stage {
                stages[stages.count - 1].handMs += chunk.handMs
            } else {
                stages.append(PerformanceStage(label: chunk.stage, handMs: chunk.handMs))
            }
            if index == playing { active = stages.count - 1 }
        }
        if playing == nil, !isFinished, !stages.isEmpty { active = stages.count - 1 }
        return (stages, active)
    }

    /// Chunks whose decoded atlases are held right now (memory bound check).
    var retainedAtlasCount: Int {
        chunks.reduce(0) { count, chunk in
            if case .ready = chunk.atlas { return count + 1 }
            return count
        }
    }
}

/// Positive and at most `RGBAPixels.maxPixelCount` pixels, without overflowing
/// on untrusted (possibly huge) dimensions.
func withinPixelBudget(_ width: Int, _ height: Int) -> Bool {
    width > 0 && height > 0 && width <= RGBAPixels.maxPixelCount / height
}
