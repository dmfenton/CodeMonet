import CoreGraphics
import Foundation
import MonetNetworking
import MonetProtocol
import MonetRender
import MonetStudio
import Observation

/// Drives the paint-mode raster layer from `MonetStudio.PaintingState`
/// (docs/program-painting.md "Live performance"): shows `base`'s
/// `final.png`, and plays a performance — a live run's `performance.bin`
/// as the server writes it, or a recorded version's complete stream — over
/// it, pasting each patch's pixels in paint order (`MonetRender
/// .PerformancePlayer`). A version without a stream (recorded before
/// performances existed) shows its `final.png` and reports done. The native
/// counterpart of `web/src/renderers/PerformancePlayer.tsx`.
///
/// Driven once per `TimelineView` tick through `frame(...)`, like
/// `CanvasView`'s strokes cache. Glue over tested pieces (`PerformanceParser`/
/// `PerformancePlayer`/`PerformanceAtlas` in MonetRender, the byte stream in
/// `PaintingAssetClient`): network I/O and atlas decoding happen in tasks,
/// and a superseded performance never touches the picture again.
@MainActor
@Observable
final class PaintingPerformanceController {
    /// Hand-time multipliers. The studio plays first versions at 3x and
    /// revisions at 1x (the web client's `LIVE_SPEED`/`LIVE_REVISION_SPEED`);
    /// either is sped up only as far as `performancePlaybackRate` needs to
    /// stay within a minute of what has arrived.
    struct Rates: Equatable {
        var firstVersion: Double
        var revision: Double
        /// Never lag what has arrived by more than this much playback time.
        var maxBehindMs: Double = performanceMaxBehindMs

        static let studio = Rates(firstVersion: 3, revision: 1)
        /// Gallery replay at the web replay's default 2x of the studio's pace:
        /// 6x from blank, 2x for revisions, at most 30 s per version.
        static let replay = Rates(firstVersion: 6, revision: 2, maxBehindMs: performanceMaxBehindMs / 2)
    }

    /// How a playback ended, for the caller to report to the store.
    enum Completion: Equatable {
        /// A recorded version (`PaintingState.playing`) finished.
        case version(assetBase: String)
        /// A live run's stream played to its end (or could not be played).
        case live(assetBase: String)
    }

    /// The performance on screen, for the stage bar.
    struct Progress: Equatable {
        var assetBase: String
        var stages: [PerformanceStage]
        /// Index into `stages` of the stage being painted; `nil` when done.
        var active: Int?
    }

    /// Bumped when an async load lands so the canvas re-renders even when
    /// its timeline is paused (a base-only painting has nothing animating).
    private(set) var revision = 0
    /// Published off the render pass, only when it changes.
    private(set) var progress: Progress?

    @ObservationIgnored private let rates: Rates
    @ObservationIgnored private let assetClient: PaintingAssetClient
    @ObservationIgnored private var target: Target = .blank
    @ObservationIgnored private var session: Session?
    /// What the canvas shows (kept across target changes until the next
    /// picture is ready, so a version change never flashes blank).
    @ObservationIgnored private var displayed: CGImage?
    /// Final pictures by `asset_base`, least recently used first.
    @ObservationIgnored private var finals: [(assetBase: String, image: CGImage)] = []
    @ObservationIgnored private var publishedProgress: Progress?

    /// Decoded final pictures kept for instant version switches (each is a
    /// full-resolution bitmap, so few).
    static let finalCacheLimit = 4
    /// Longest wall-clock step one frame may play: after a stall (the app
    /// was backgrounded, the timeline paused) playback resumes rather than
    /// jumping; the backlog rate still catches up with a live run.
    static let maxFrameMs = 100.0

    init(rates: Rates = .studio, assetClient: PaintingAssetClient = PaintingAssetClient()) {
        self.rates = rates
        self.assetClient = assetClient
    }

    // MARK: - Target

    private enum Kind: Equatable {
        case version
        case live
    }

    private enum Target: Equatable {
        case blank
        /// A settled version: its final picture.
        case still(PaintingVersionRef)
        /// A performance playing over `base`.
        case performance(assetBase: String, kind: Kind, base: PaintingVersionRef?)
        /// A live run played to its end, awaiting the server's verdict:
        /// keep the last picture.
        case holding(assetBase: String)
    }

    private static func target(for painting: PaintingState) -> Target {
        if let live = painting.live {
            return live.played
                ? .holding(assetBase: live.ref.assetBase)
                : .performance(assetBase: live.ref.assetBase, kind: .live, base: painting.base)
        }
        if let playing = painting.playing {
            return .performance(assetBase: playing.assetBase, kind: .version, base: painting.base)
        }
        if let base = painting.base { return .still(base) }
        return .blank
    }

    // MARK: - Per frame

    /// Called once per `TimelineView` tick. Synchronous: starts loads in the
    /// background and returns what is on screen now. `onDone` is called
    /// (outside the render pass) once per finished playback.
    func frame(
        painting: PaintingState,
        apiBaseURL: URL,
        now: Date = Date(),
        onDone: @escaping (Completion) -> Void
    ) -> CGImage? {
        _ = revision  // observe async loads
        let next = Self.target(for: painting)
        if next != target {
            target = next
            begin(next, apiBaseURL: apiBaseURL, onDone: onDone)
        }
        if let session { tick(session, now: now, onDone: onDone) }
        return displayed
    }

    /// Nothing to show (the canvas left paint mode, or the view went away):
    /// stops any stream so it doesn't outlive the canvas.
    func idle() {
        guard target != .blank || session != nil else { return }
        target = .blank
        session?.cancel()
        session = nil
        displayed = nil
        publishProgress(nil)
    }

    private func begin(_ target: Target, apiBaseURL: URL, onDone: @escaping (Completion) -> Void) {
        session?.cancel()
        session = nil
        switch target {
        case .blank:
            displayed = nil
            publishProgress(nil)
        case let .still(ref):
            publishProgress(nil)
            if let cached = cachedFinal(ref.assetBase) { displayed = cached }
            // Also when a played stream's (lossy) last picture is cached:
            // swap in the exact final.png.
            if cachedFinal(ref.assetBase, exactOnly: true) == nil {
                Task { [weak self] in
                    guard let self, let image = await self.loadFinal(ref.assetBase, apiBaseURL: apiBaseURL),
                          self.target == target else { return }
                    self.displayed = image
                    self.revision += 1
                }
            }
        case let .performance(assetBase, kind, base):
            // Starts from the base picture (blank for a first version); an
            // uncached base keeps what is on screen until it loads.
            if let base {
                if let cached = cachedFinal(base.assetBase) { displayed = cached }
            } else {
                displayed = nil
            }
            let session = Session(assetBase: assetBase, kind: kind)
            self.session = session
            session.ingest = Task { [weak self] in
                await self?.ingest(session, base: base, apiBaseURL: apiBaseURL, onDone: onDone)
            }
        case .holding:
            publishProgress(nil)
        }
    }

    private func tick(_ session: Session, now: Date, onDone: @escaping (Completion) -> Void) {
        guard let player = session.player, !session.reported else { return }
        scheduleDecode(session, player: player)
        let wallMs = session.lastTick.map { min(now.timeIntervalSince($0) * 1000, Self.maxFrameMs) } ?? 0
        session.lastTick = now
        player.advance(
            byMs: wallMs,
            baseRate: player.isRevision ? rates.revision : rates.firstVersion,
            maxBehindMs: rates.maxBehindMs
        )
        if let image = player.takeImageIfChanged() { displayed = image }
        let stages = player.stages
        publishProgress(Progress(assetBase: session.assetBase, stages: stages.stages, active: stages.active))
        if player.isFinished { finish(session, cachePicture: !player.failed, onDone: onDone) }
    }

    /// One atlas decode at a time, off the main thread.
    private func scheduleDecode(_ session: Session, player: PerformancePlayer) {
        guard !session.decoding, let request = player.nextChunkToDecode() else { return }
        session.decoding = true
        Task { [weak session] in
            let atlas = await Task.detached(priority: .userInitiated) {
                try? PerformanceAtlas.decode(color: request.color, order: request.order)
            }.value
            guard let session, !session.cancelled else { return }
            session.player?.chunkDecoded(request.chunk, atlas: atlas)
            session.decoding = false
        }
    }

    /// Reports the playback done. A stream played to its end leaves that
    /// version's final picture on screen (`cachePicture`; swapped for the
    /// exact `final.png` once the store settles on it).
    private func finish(_ session: Session, cachePicture: Bool, onDone: @escaping (Completion) -> Void) {
        session.reported = true
        if cachePicture, let displayed {
            cacheFinal(session.assetBase, displayed, exact: false)
        }
        publishProgress(nil)
        let completion: Completion = session.kind == .live
            ? .live(assetBase: session.assetBase)
            : .version(assetBase: session.assetBase)
        Task { onDone(completion) }
    }

    // MARK: - Streaming

    private func ingest(_ session: Session, base: PaintingVersionRef?, apiBaseURL: URL, onDone: @escaping (Completion) -> Void) async {
        var baseImage: CGImage?
        if let base { baseImage = await loadFinal(base.assetBase, apiBaseURL: apiBaseURL) }
        guard !session.cancelled else { return }
        let url = PaintingAssetURL.paintingAssetUrl(
            apiBase: apiBaseURL.absoluteString, assetBase: session.assetBase, file: PaintingAssetURL.performanceFile
        )
        var parser = PerformanceParser()
        do {
            for try await bytes in assetClient.byteStream(at: url) {
                guard !session.cancelled else { return }
                for frame in parser.push(bytes) {
                    if let player = session.player {
                        player.ingest(frame)
                    } else if let player = PerformancePlayer(header: frame.meta, base: baseImage) {
                        session.player = player
                        revision += 1  // start ticking from the base picture
                    } else {
                        throw StreamError.badHeader
                    }
                }
            }
            guard !session.cancelled else { return }
            guard let player = session.player else { throw StreamError.badHeader }
            player.finishStream()
        } catch {
            guard !session.cancelled else { return }
            await fallBack(session, apiBaseURL: apiBaseURL, onDone: onDone)
        }
    }

    private enum StreamError: Error { case badHeader }

    /// No playable stream (a version from before performances, a failed
    /// run's discarded directory, a network error): a version shows its
    /// final picture; a live run reports done and holds what is on screen
    /// until the server confirms or fails it.
    private func fallBack(_ session: Session, apiBaseURL: URL, onDone: @escaping (Completion) -> Void) async {
        if session.kind == .version, let image = await loadFinal(session.assetBase, apiBaseURL: apiBaseURL) {
            guard !session.cancelled else { return }
            displayed = image
            revision += 1
        }
        guard !session.cancelled, !session.reported else { return }
        session.player = nil
        finish(session, cachePicture: false, onDone: onDone)
    }

    // MARK: - Final pictures

    private func loadFinal(_ assetBase: String, apiBaseURL: URL) async -> CGImage? {
        if let cached = cachedFinal(assetBase, exactOnly: true) { return cached }
        let url = PaintingAssetURL.paintingAssetUrl(
            apiBase: apiBaseURL.absoluteString, assetBase: assetBase, file: PaintingAssetURL.finalFile
        )
        guard let data = try? await assetClient.imageData(at: url),
              let image = try? PaintingImageDecoder.decode(data) else {
            return cachedFinal(assetBase)
        }
        cacheFinal(assetBase, image, exact: true)
        return image
    }

    @ObservationIgnored private var exactFinals: Set<String> = []

    private func cachedFinal(_ assetBase: String, exactOnly: Bool = false) -> CGImage? {
        guard let index = finals.firstIndex(where: { $0.assetBase == assetBase }) else { return nil }
        if exactOnly, !exactFinals.contains(assetBase) { return nil }
        let entry = finals.remove(at: index)
        finals.append(entry)
        return entry.image
    }

    /// `exact`: the server's `final.png` (a played stream's last picture is
    /// lossy; the still view refetches the exact one).
    private func cacheFinal(_ assetBase: String, _ image: CGImage, exact: Bool) {
        finals.removeAll { $0.assetBase == assetBase }
        finals.append((assetBase, image))
        if exact { exactFinals.insert(assetBase) } else { exactFinals.remove(assetBase) }
        while finals.count > Self.finalCacheLimit {
            exactFinals.remove(finals.removeFirst().assetBase)
        }
    }

    // MARK: - Progress

    /// Deferred to the next main-actor turn: `frame()` runs inside a render
    /// pass, which must not mutate observed state.
    private func publishProgress(_ next: Progress?) {
        guard next != publishedProgress else { return }
        publishedProgress = next
        Task { [weak self] in
            guard let self, self.progress != next else { return }
            self.progress = next
        }
    }

    // MARK: - Session

    /// One performance being played; dropped (and its stream cancelled)
    /// when the target changes.
    private final class Session {
        let assetBase: String
        let kind: Kind
        var player: PerformancePlayer?
        var ingest: Task<Void, Never>?
        var decoding = false
        var lastTick: Date?
        var reported = false
        private(set) var cancelled = false

        init(assetBase: String, kind: Kind) {
            self.assetBase = assetBase
            self.kind = kind
        }

        func cancel() {
            cancelled = true
            ingest?.cancel()
        }
    }
}
