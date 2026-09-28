import CoreGraphics
import Foundation
@testable import MonetRender
import Testing

// MARK: - Synthetic streams

private func part(_ bytes: Data) -> Data {
    var length = UInt32(bytes.count).littleEndian
    return Data(bytes: &length, count: 4) + bytes
}

private func frame(_ meta: String, index: Data = Data(), color: Data = Data(), order: Data = Data([7])) -> Data {
    [Data(meta.utf8), index, color, order].map(part).reduce(Data(), +)
}

private func record(_ p: PerformancePatch) -> Data {
    var data = Data()
    for value in [Float(p.t), Float(p.dur)] {
        var bits = value.bitPattern.littleEndian
        data.append(Data(bytes: &bits, count: 4))
    }
    for value in [p.ax, p.ay, p.w, p.h, p.x, p.y] {
        var u16 = UInt16(value).littleEndian
        data.append(Data(bytes: &u16, count: 2))
    }
    return data
}

private let patch = PerformancePatch(t: 100, dur: 200, ax: 0, ay: 8, w: 16, h: 12, x: 40, y: 30)
private let stream = frame(#"{"kind":"header","width":160,"height":120,"format":1}"#)
    + frame(#"{"kind":"chunk","stage":"sky","atlas":[64,32],"patches":1}"#, index: record(patch))
    + frame(#"{"kind":"end","ms":300}"#)

/// Mirrors `web/src/test/performanceStream.test.ts`.
@Suite("Performance stream")
struct PerformanceStreamTests {
    @Test("parses frames however the bytes are split")
    func parsesAnySplit() throws {
        for size in [1, 3, 17, stream.count] {
            var parser = PerformanceParser()
            var frames: [PerformanceFrame] = []
            var offset = 0
            while offset < stream.count {
                let end = min(offset + size, stream.count)
                frames += try parser.push(stream.subdata(in: offset ..< end))
                offset = end
            }
            #expect(frames.map(\.meta) == [
                .header(width: 160, height: 120, format: 1, base: .blank),
                .chunk(stage: "sky", atlasWidth: 64, atlasHeight: 32, patches: 1),
                .end(ms: 300),
            ])
            #expect(decodePerformancePatches(frames[1].index) == [patch])
            #expect(frames[1].order == Data([7]))
        }
    }

    @Test("holds back an incomplete frame")
    func holdsIncompleteFrame() throws {
        var parser = PerformanceParser()
        #expect(try parser.push(stream.prefix(10)).isEmpty)
    }

    @Test("refuses a frame claiming more than the limit instead of buffering for it")
    func refusesHugeFrame() {
        // The stream is written by the painting program: a part may claim ~2 GB.
        var parser = PerformanceParser()
        #expect(throws: PerformanceParser.StreamError.self) {
            _ = try parser.push(Data([0xFF, 0xFF, 0xFF, 0x7F]))
        }
    }

    @Test("reads a revision header, an error frame, unknown kinds and garbage")
    func metaKinds() throws {
        var parser = PerformanceParser()
        let frames = try parser.push(
            frame(#"{"kind":"header","width":8,"height":4,"format":1,"base":"previous"}"#)
                + frame(#"{"kind":"future"}"#) + frame(#"{"kind":"error"}"#) + frame("not json")
        )
        #expect(frames.map(\.meta) == [
            .header(width: 8, height: 4, format: 1, base: .previous), .unknown(kind: "future"), .error, .malformed,
        ])
    }

    @Test("reveals a patch along its draw order over [t, t + dur]")
    func orderThreshold() {
        #expect(performanceOrderThreshold(patch, now: 50) == 0)
        #expect(abs(performanceOrderThreshold(patch, now: 200) - 128) < 1e-9)
        #expect(performanceOrderThreshold(patch, now: 300) == 256)
        #expect(performanceOrderThreshold(PerformancePatch(t: 5, dur: 0, ax: 0, ay: 0, w: 1, h: 1, x: 0, y: 0), now: 5) == 256)
    }

    @Test("skips patches outside the picture or atlases")
    func patchBounds() {
        let picture = PixelSize(width: 160, height: 120)
        let color = PixelSize(width: 64, height: 32)
        let order = PixelSize(width: 16, height: 8)
        func fits(_ p: PerformancePatch, order o: PixelSize = order) -> Bool {
            performancePatchFits(p, picture: picture, color: color, order: o)
        }
        #expect(fits(patch))
        var outside = patch
        outside.x = 150
        #expect(!fits(outside))
        var belowAtlas = patch
        belowAtlas.ay = 24
        #expect(!fits(belowAtlas))
        var empty = patch
        empty.w = 0
        #expect(!fits(empty))
        var notFinite = patch
        notFinite.t = .nan
        #expect(!fits(notFinite))
        #expect(!fits(patch, order: PixelSize(width: 3, height: 8)))
    }

    @Test("plays at the base rate while little is waiting; speeds up so a big backlog plays within a minute")
    func playbackRate() {
        #expect(performancePlaybackRate(baseRate: 1, backlogMs: 5000) == 1)
        #expect(abs(performancePlaybackRate(baseRate: 1, backlogMs: 600_000) - 10) < 1e-9)
        #expect(abs(performancePlaybackRate(baseRate: 3, backlogMs: 600_000, maxBehindMs: 60000) - 10) < 1e-9)
        // A short stroke is slowed so it stays on screen long enough to see...
        #expect(abs(performancePlaybackRate(baseRate: 3, backlogMs: 5000, activeDurMs: 90) - 90.0 / 400) < 1e-9)
        #expect(performancePlaybackRate(baseRate: 3, backlogMs: 5000, activeDurMs: 2000) == 3)
        // ...but catching up wins (dense paintings keep their proportions).
        #expect(abs(performancePlaybackRate(baseRate: 3, backlogMs: 1_200_000, activeDurMs: 30) - 20) < 1e-9)
    }
}

// MARK: - Real streams

/// Real streams written by the server's paint library. Regenerate with (from
/// `server/`): `uv run python -m code_monet.paint_runner --program
/// ../ios/MonetKit/Tests/Fixtures/performance/v1/painting.py --out <dir>
/// --width 320 --height 240` (v2: its own program, `--previous <v1 dir>`),
/// then copy `performance.bin` and `final.png`. `v1/pasted.png` is every
/// v1 patch pasted whole in order, computed in Python with PIL's WebP
/// decoder — the reference for this decoder and paste.
private enum Fixture {
    static let directory = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Fixtures/performance")

    static func data(_ path: String) throws -> Data {
        try Data(contentsOf: directory.appendingPathComponent(path))
    }

    static func frames(_ version: String) throws -> [PerformanceFrame] {
        var parser = PerformanceParser()
        return try parser.push(try data("\(version)/performance.bin"))
    }

    static func pixels(_ path: String) throws -> RGBAPixels {
        try PaintingImageDecoder.decodeRGBA(try data(path))
    }
}

/// Mean absolute difference over RGB channels.
private func meanDifference(_ a: RGBAPixels, _ b: RGBAPixels) -> Double {
    precondition(a.width == b.width && a.height == b.height)
    var total = 0
    for index in 0 ..< a.width * a.height {
        for channel in 0 ..< 3 {
            total += abs(Int(a.bytes[index * 4 + channel]) - Int(b.bytes[index * 4 + channel]))
        }
    }
    return Double(total) / Double(a.width * a.height * 3)
}

/// Decodes every chunk the player asks for, synchronously (the app does
/// this off the main thread).
private func decodeRequested(_ player: PerformancePlayer) {
    while let request = player.nextChunkToDecode() {
        player.chunkDecoded(request.chunk, atlas: try? PerformanceAtlas.decode(color: request.color, order: request.order))
    }
}

private func playToEnd(_ player: PerformancePlayer, stepMs: Double = 16, rate: Double = 3) -> Int {
    var steps = 0
    while !player.isFinished, steps < 100_000 {
        decodeRequested(player)
        player.advance(byMs: stepMs, baseRate: rate)
        steps += 1
    }
    return steps
}

@Suite("Performance player (real streams)")
struct PerformancePlayerTests {
    @Test("a real stream parses into its header, chunks and end")
    func realStreamStructure() throws {
        let frames = try Fixture.frames("v1")
        #expect(frames.first?.meta == .header(width: 320, height: 240, format: 1, base: .blank))
        #expect(frames.last?.meta == .end(ms: 3368.5))
        let chunks = frames.compactMap { frame -> (String, Int)? in
            guard case let .chunk(stage, _, _, count) = frame.meta else { return nil }
            #expect(decodePerformancePatches(frame.index).count == count)
            return (stage, count)
        }
        #expect(chunks.map(\.0) == ["ground", "sky", "hills"])
        #expect(chunks.map(\.1) == [1, 27, 1])
        let revision = try Fixture.frames("v2")
        #expect(revision.first?.meta == .header(width: 320, height: 240, format: 1, base: .previous))
    }

    @Test("decodes the lossless order atlas exactly (sum matches the server's PIL decode)")
    func orderAtlasDecodesExactly() throws {
        let sky = try #require(try Fixture.frames("v1").first {
            if case .chunk(stage: "sky", _, _, _) = $0.meta { return true }
            return false
        })
        let atlas = try PerformanceAtlas.decode(color: sky.color, order: sky.order)
        #expect(atlas.color.width == 2048)
        #expect(atlas.color.height == 52)
        #expect(atlas.orderSize == PixelSize(width: 512, height: 13))
        #expect(atlas.order.reduce(0) { $0 + Int($1) } == 407_132)
    }

    @Test("playing a first version to the end reproduces the server's paste and its final.png")
    func playsFirstVersionToFinal() throws {
        let frames = try Fixture.frames("v1")
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: nil))
        #expect(!player.isRevision)
        frames.dropFirst().forEach(player.ingest)
        let steps = playToEnd(player)
        #expect(player.isFinished)
        // 3368.5 hand ms at 3x in 16 ms frames is about 70 frames; short strokes
        // are held on screen for at least performanceMinStrokeMs, so more.
        #expect(steps >= 70)
        #expect(steps < 70 + fixtureStrokes(frames) * Int(performanceMinStrokeMs / 16) + 10)
        #expect(meanDifference(player.pixels, try Fixture.pixels("v1/pasted.png")) < 0.5)
        #expect(meanDifference(player.pixels, try Fixture.pixels("v1/final.png")) < 4)
        #expect(player.retainedAtlasCount == 0)
        #expect(player.takeImageIfChanged()?.width == 320)
        #expect(player.takeImageIfChanged() == nil)
    }

    @Test("a revision plays over the previous version's final picture")
    func playsRevisionOverBase() throws {
        let frames = try Fixture.frames("v2")
        let base = try PaintingImageDecoder.decode(try Fixture.data("v1/final.png"))
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: base))
        #expect(player.isRevision)
        frames.dropFirst().forEach(player.ingest)
        _ = playToEnd(player, rate: 1)
        #expect(player.isFinished)
        #expect(meanDifference(player.pixels, try Fixture.pixels("v2/final.png")) < 2)
    }

    @Test("mid-stroke, only the pixels drawn so far are pasted")
    func pastesInFlightPatchPartially() throws {
        let frames = try Fixture.frames("v1")
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: nil))
        frames.dropFirst().forEach(player.ingest)
        decodeRequested(player)
        // The hills stroke is one patch over [3159.0, 3368.5]: stop before
        // it, then halfway through it.
        player.advance(byMs: 3150, baseRate: 1)
        let before = player.pixels
        player.advance(byMs: 114, baseRate: 1)
        let midway = player.pixels
        _ = playToEnd(player)
        let final = player.pixels
        let pasted = try Fixture.pixels("v1/pasted.png")
        // Of the pixels the stroke changes (inside its patch, x 10..<307,
        // y 129..<179), some are painted already and some are still to come.
        var painted = 0
        var pending = 0
        for y in 129 ..< 179 {
            for x in 10 ..< 307 {
                let i = (y * 320 + x) * 4
                let differs = { (a: RGBAPixels, b: RGBAPixels) in (0 ..< 3).contains { a.bytes[i + $0] != b.bytes[i + $0] } }
                guard differs(final, before) else { continue }
                if differs(final, midway) { pending += 1 } else { painted += 1 }
            }
        }
        #expect(painted > 100)
        #expect(pending > 100)
        #expect(meanDifference(final, pasted) < 0.5)
    }

    @Test("never plays past what has arrived, and ends only once the stream is complete")
    func waitsForArrivals() throws {
        let frames = try Fixture.frames("v1")
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: nil))
        player.ingest(frames[1])
        player.ingest(frames[2])
        for _ in 0 ..< 100 {
            decodeRequested(player)
            player.advance(byMs: 1000, baseRate: 3)
        }
        let skyEnd = decodePerformancePatches(frames[2].index).map(\.end).max() ?? 0
        #expect(player.handMs <= skyEnd)
        #expect(!player.isFinished)
        #expect(player.stages.active == 1)
        frames.dropFirst(3).forEach(player.ingest)
        _ = playToEnd(player)
        #expect(player.isFinished)
        #expect(player.stages.stages.map(\.label) == ["ground", "sky", "hills"])
        #expect(player.stages.active == nil)
    }

    @Test("waits for a chunk's atlases before playing into it")
    func waitsForDecode() throws {
        let frames = try Fixture.frames("v1")
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: nil))
        frames.dropFirst().forEach(player.ingest)
        player.advance(byMs: 100_000, baseRate: 3)
        #expect(player.handMs == 0)
        #expect(player.pixels == RGBAPixels(width: 320, height: 240))
        _ = playToEnd(player)
        #expect(player.isFinished)
    }

    @Test("an undecodable chunk is skipped, not stalled on")
    func skipsUndecodableChunk() throws {
        var parser = PerformanceParser()
        let frames = try parser.push(stream)
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: nil))
        frames.dropFirst().forEach(player.ingest)
        _ = playToEnd(player)
        #expect(player.isFinished)
        #expect(player.pixels == RGBAPixels(width: 160, height: 120))
    }

    @Test("an error frame ends the stream after what has arrived")
    func errorEndsStream() throws {
        let frames = try Fixture.frames("v1")
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: nil))
        player.ingest(frames[1])
        player.ingest(PerformanceFrame(meta: .error))
        _ = playToEnd(player)
        #expect(player.failed)
        #expect(player.isFinished)
    }

    @Test("refuses a header too large to allocate")
    func refusesHugeHeader() {
        #expect(PerformancePlayer(header: .header(width: 100_000, height: 100_000, format: 1, base: .blank), base: nil) == nil)
        #expect(PerformancePlayer(header: .header(width: 0, height: 10, format: 1, base: .blank), base: nil) == nil)
        #expect(PerformancePlayer(header: .end(ms: 0), base: nil) == nil)
        // Dimensions whose product overflows Int: refused, not a trap.
        #expect(PerformancePlayer(header: .header(width: Int.max, height: 2, format: 1, base: .blank), base: nil) == nil)
    }

    @Test("an atlas size that would overflow is skipped, not a trap")
    func skipsOverflowingAtlas() throws {
        let frames = try Fixture.frames("v1")
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: nil))
        let huge = PerformanceFrame(
            meta: .chunk(stage: "x", atlasWidth: Int.max, atlasHeight: Int.max, patches: 1),
            index: frames[2].index, color: frames[2].color, order: frames[2].order
        )
        player.ingest(huge)
        frames.dropFirst().forEach(player.ingest)
        _ = playToEnd(player)
        #expect(player.isFinished)
    }

    @Test("a stream painted from blank starts white even when given a picture")
    func blankStreamIgnoresBase() throws {
        let frames = try Fixture.frames("v1")
        let base = try PaintingImageDecoder.decode(try Fixture.data("v1/final.png"))
        let player = try #require(PerformancePlayer(header: frames[0].meta, base: base))
        #expect(!player.isRevision)
        #expect(player.pixels == RGBAPixels(width: 320, height: 240))
    }
}

/// Number of patches (strokes) in a fixture stream.
private func fixtureStrokes(_ frames: [PerformanceFrame]) -> Int {
    frames.reduce(0) { total, frame in
        if case let .chunk(_, _, _, count) = frame.meta { return total + count }
        return total
    }
}
