import Foundation

// The performance stream (docs/program-painting.md "Live performance",
// server/code_monet/paintlib/performance.py): the pixels each paint op
// changed, in paint order, with one-hand timing. Swift port of
// shared/src/renderer/performance.ts — platform-independent parsing and
// scheduling; `PerformancePlayer` decodes the atlases and pastes pixels.
//
//   frame := part(json) part(index) part(color) part(order);  part := u32le len | bytes

/// A version's performance stream, next to its other assets.
public let performanceFile = PaintingAssetURL.performanceFile

/// The order atlas is this many times smaller than the color atlas.
public let performanceOrderScale = 4

/// A live performance never lags what has arrived by more than this much
/// video time (`PERFORMANCE_MAX_BEHIND_MS`).
public let performanceMaxBehindMs = 60_000.0

/// What a stream is performed over.
public enum PerformanceBase: String, Equatable, Sendable {
    /// A first version: painted from a blank canvas.
    case blank
    /// A revision: performed over the previous version's `final.png`.
    case previous
}

/// A frame's JSON part.
public enum PerformanceMeta: Equatable, Sendable {
    case header(width: Int, height: Int, format: Int, base: PerformanceBase)
    case chunk(stage: String, atlasWidth: Int, atlasHeight: Int, patches: Int)
    /// The stream is complete; `ms` is the total hand time.
    case end(ms: Double)
    /// The program raised; nothing more follows.
    case error
    /// A kind this client doesn't know (a newer format): skipped.
    case unknown(kind: String)
    /// Not a JSON object with a `kind`: the stream is garbage from here on.
    case malformed

    init(json: Data) {
        guard let object = try? JSONSerialization.jsonObject(with: json) as? [String: Any],
              let kind = object["kind"] as? String
        else {
            self = .malformed
            return
        }
        func int(_ value: Any?) -> Int? { (value as? NSNumber).map { $0.intValue } }
        switch kind {
        case "header":
            guard let width = int(object["width"]), let height = int(object["height"]) else {
                self = .malformed
                return
            }
            let base = (object["base"] as? String).flatMap(PerformanceBase.init(rawValue:)) ?? .blank
            self = .header(width: width, height: height, format: int(object["format"]) ?? 1, base: base)
        case "chunk":
            let atlas = object["atlas"] as? [Any]
            guard let atlas, atlas.count == 2, let aw = int(atlas[0]), let ah = int(atlas[1]) else {
                self = .malformed
                return
            }
            self = .chunk(
                stage: object["stage"] as? String ?? "",
                atlasWidth: aw,
                atlasHeight: ah,
                patches: int(object["patches"]) ?? 0
            )
        case "end":
            self = .end(ms: (object["ms"] as? NSNumber)?.doubleValue ?? 0)
        case "error":
            self = .error
        default:
            self = .unknown(kind: kind)
        }
    }
}

/// One complete frame.
public struct PerformanceFrame: Equatable, Sendable {
    public var meta: PerformanceMeta
    /// Patch records (`decodePerformancePatches`).
    public var index: Data
    /// Lossy WebP atlas (RGB) holding each patch's rect.
    public var color: Data
    /// Lossless WebP atlas at 1/`performanceOrderScale` resolution: per
    /// 4x4 block, 1...255 = draw order, 0 = nothing changed there.
    public var order: Data

    public init(meta: PerformanceMeta, index: Data = Data(), color: Data = Data(), order: Data = Data()) {
        self.meta = meta
        self.index = index
        self.color = color
        self.order = order
    }
}

/// One patch: pixels of one op, pasted into the picture over `[t, t + dur]`
/// (hand time, ms).
public struct PerformancePatch: Equatable, Sendable {
    public var t: Double
    public var dur: Double
    /// Top-left in the color atlas (px); the order atlas is at 1/`performanceOrderScale`.
    public var ax: Int
    public var ay: Int
    public var w: Int
    public var h: Int
    /// Top-left in the picture (px).
    public var x: Int
    public var y: Int

    public init(t: Double, dur: Double, ax: Int, ay: Int, w: Int, h: Int, x: Int, y: Int) {
        self.t = t
        self.dur = dur
        self.ax = ax
        self.ay = ay
        self.w = w
        self.h = h
        self.x = x
        self.y = y
    }

    public var end: Double { t + dur }
}

/// Incremental frame parser: push bytes as they arrive, take complete frames.
public struct PerformanceParser: Sendable {
    /// Largest frame a stream may carry. The stream is written by the painting
    /// program's process, so a frame may claim any length; one this large is
    /// an error, not something to buffer while waiting for it.
    public static let maxFrameBytes = 64 * 1024 * 1024

    public enum StreamError: Error, Equatable { case frameTooLarge(Int) }

    private var buffer: [UInt8] = []
    /// Start of the first unparsed frame in `buffer`.
    private var start = 0

    public init() {}

    public mutating func push(_ bytes: Data) throws -> [PerformanceFrame] {
        buffer.append(contentsOf: bytes)
        var frames: [PerformanceFrame] = []
        while let (frame, next) = try frame(at: start) {
            frames.append(frame)
            start = next
        }
        // Compact once the consumed prefix dominates the buffer.
        if start > 0, start >= buffer.count / 2 {
            buffer.removeFirst(start)
            start = 0
        }
        return frames
    }

    private func frame(at offset: Int) throws -> (PerformanceFrame, Int)? {
        var parts: [Data] = []
        var cursor = offset
        for _ in 0 ..< 4 {
            guard cursor + 4 <= buffer.count else { return nil }
            let length = Int(readUInt32LE(buffer, cursor))
            let size = cursor + 4 + length - offset
            guard size <= Self.maxFrameBytes else { throw StreamError.frameTooLarge(size) }
            guard length <= buffer.count - cursor - 4 else { return nil }
            parts.append(Data(buffer[(cursor + 4) ..< (cursor + 4 + length)]))
            cursor += 4 + length
        }
        let frame = PerformanceFrame(meta: PerformanceMeta(json: parts[0]), index: parts[1], color: parts[2], order: parts[3])
        return (frame, cursor)
    }
}

private let patchRecordBytes = 20

/// Decodes a chunk's index part: 20-byte little-endian records of
/// `f32 t_ms, f32 dur_ms, u16 atlas_x, atlas_y, w, h, x, y`. A trailing
/// partial record is ignored.
public func decodePerformancePatches(_ index: Data) -> [PerformancePatch] {
    let bytes = [UInt8](index)
    var patches: [PerformancePatch] = []
    patches.reserveCapacity(bytes.count / patchRecordBytes)
    var offset = 0
    while offset + patchRecordBytes <= bytes.count {
        func u16(_ at: Int) -> Int { Int(bytes[offset + at]) | Int(bytes[offset + at + 1]) << 8 }
        patches.append(PerformancePatch(
            t: Double(Float(bitPattern: readUInt32LE(bytes, offset))),
            dur: Double(Float(bitPattern: readUInt32LE(bytes, offset + 4))),
            ax: u16(8),
            ay: u16(10),
            w: u16(12),
            h: u16(14),
            x: u16(16),
            y: u16(18)
        ))
        offset += patchRecordBytes
    }
    return patches
}

/// Pixel size of a picture or atlas, for `performancePatchFits`.
public struct PixelSize: Equatable, Sendable {
    public var width: Int
    public var height: Int

    public init(width: Int, height: Int) {
        self.width = width
        self.height = height
    }
}

/// Whether a patch lies inside the picture and its atlases. The stream is the
/// painting program's output (untrusted): patches that don't fit are skipped.
public func performancePatchFits(_ p: PerformancePatch, picture: PixelSize, color: PixelSize, order: PixelSize) -> Bool {
    let k = performanceOrderScale
    return p.w > 0
        && p.h > 0
        && p.t.isFinite
        && p.dur.isFinite
        && p.x + p.w <= picture.width
        && p.y + p.h <= picture.height
        && p.ax + p.w <= color.width
        && p.ay + p.h <= color.height
        && (p.ax + p.w + k - 1) / k <= order.width
        && (p.ay + p.h + k - 1) / k <= order.height
}

/// Order threshold (1...255) revealed `now` ms into a patch: pixels whose
/// order value is <= this are painted. `256` = the whole patch (done), `0` =
/// not started. Order 0 (nothing changed there) lands at the end.
public func performanceOrderThreshold(_ patch: PerformancePatch, now: Double) -> Double {
    if now >= patch.t + patch.dur { return 256 }
    if now < patch.t { return 0 }
    let progress = patch.dur > 0 ? (now - patch.t) / patch.dur : 1
    return 1 + progress * 254
}

/// Each stroke is on screen at least this long (wall ms) unless catching up,
/// so a sparse painting's strokes are seen landing one by one.
public let performanceMinStrokeMs: Double = 400

/// Playback rate (hand ms per ms), mirroring the web `playbackRate`: normally
/// the base rate, but a stroke in flight (`activeDurMs` of hand time) is
/// slowed to take at least `minStrokeMs` on screen; and playback speeds up
/// whenever the received-but-unplayed hand time (`backlogMs`) would take
/// longer than `maxBehindMs` (catching up wins). Dense paintings are always
/// catching up, so their time stays proportional to their strokes' hand
/// time; sparse ones play stroke by stroke.
public func performancePlaybackRate(
    baseRate: Double,
    backlogMs: Double,
    maxBehindMs: Double = performanceMaxBehindMs,
    activeDurMs: Double? = nil,
    minStrokeMs: Double = performanceMinStrokeMs
) -> Double {
    let catchUp = backlogMs / maxBehindMs
    let legible = activeDurMs.map { $0 > 0 ? $0 / minStrokeMs : Double.infinity } ?? .infinity
    return max(catchUp, min(baseRate, legible))
}

private func readUInt32LE(_ bytes: [UInt8], _ offset: Int) -> UInt32 {
    UInt32(bytes[offset]) | UInt32(bytes[offset + 1]) << 8 | UInt32(bytes[offset + 2]) << 16 | UInt32(bytes[offset + 3]) << 24
}
