import CoreGraphics
import Foundation
import MonetNetworking
import MonetProtocol
import MonetRender

/// Drives the paint-mode raster layer: fetches a program-painting version's
/// `reveal.json` + keyframe/final images (program-painting spec §3-4) and
/// composites them into a `CGImage` `CanvasView` can display, advancing the
/// reveal one `TimelineView` tick at a time. The native counterpart of
/// `app/src/renderers/RasterRevealLayer.tsx` (see that file's doc comment
/// for the shared effect/generation-cancellation model this mirrors) —
/// driven from `CanvasView.frame(state:canvasSize:)` exactly like
/// `IncrementalCanvasCache`, so both layers share one per-frame call site
/// instead of a second animation driver.
///
/// Not itself a pure/testable value type (it does real network I/O and owns
/// a live `CGContext`) — `RasterRevealSink` and `MonetNetworking
/// .PaintingAssetClient` are the pieces of this that *are* unit-tested;
/// this class is glue, kept deliberately thin.
@MainActor
final class PaintingRevealController {
    private let assetClient: PaintingAssetClient

    // MARK: - What's currently loaded / being loaded

    private var loadedBaseKey = ""
    private var loadedPlayingKey = ""
    /// Bumped on every `startLoad`; an in-flight fetch task checks this
    /// before touching any state, so a version superseded mid-fetch can
    /// never clobber a newer one's result (mirrors RasterRevealLayer.tsx's
    /// `gen`/`genRef`).
    private var generation = 0

    // MARK: - What's on screen right now

    /// The static image shown when nothing is actively revealing — `base`'s
    /// `final.png`, decoded, or `nil` for a blank canvas.
    private var staticImage: CGImage?

    // MARK: - Active reveal playback, if any

    private var plan: RevealPlan?
    private var sink: RasterRevealSink?
    private var cursor = RevealCursor()
    private var playbackStartedAt: Date?
    private var playingAssetBase: String?
    /// `playing`'s own `final.png`, fetched alongside the manifest so the
    /// reveal can end on a pixel-exact image rather than the last
    /// keyframe's (which is only ever "close" — program-painting spec
    /// §4.2's "optional: without it the last keyframe... stays").
    private var finalImageForPlayback: CGImage?
    private var lastRevealImage: CGImage?

    init(assetClient: PaintingAssetClient = PaintingAssetClient()) {
        self.assetClient = assetClient
    }

    /// Called once per `TimelineView` tick from `CanvasView`. Synchronous —
    /// kicks off async loads in the background and returns whatever's
    /// already known to be on screen; `CanvasView` re-reads this every tick
    /// so the image updates as loads/playback progress.
    func frame(
        base: PaintingVersionRef?,
        playing: PaintingVersionRef?,
        apiBaseURL: URL,
        now: Date = Date(),
        onPlaybackDone: @escaping (String) -> Void
    ) -> CGImage? {
        let baseKey = base?.assetBase ?? ""
        let playingKey = playing?.assetBase ?? ""
        if baseKey != loadedBaseKey || playingKey != loadedPlayingKey {
            loadedBaseKey = baseKey
            loadedPlayingKey = playingKey
            startLoad(base: base, playing: playing, apiBaseURL: apiBaseURL, onPlaybackDone: onPlaybackDone)
        }
        if plan != nil {
            advancePlayback(now: now, onPlaybackDone: onPlaybackDone)
            return lastRevealImage
        }
        return staticImage
    }

    // MARK: - Loading

    private func startLoad(
        base: PaintingVersionRef?,
        playing: PaintingVersionRef?,
        apiBaseURL: URL,
        onPlaybackDone: @escaping (String) -> Void
    ) {
        generation += 1
        let gen = generation

        // A reveal already in flight is being superseded (a newer version
        // arrived mid-reveal, or the piece/gallery view changed out from
        // under it): jump it straight to its own fully-revealed state
        // rather than leaving it visually frozen mid-wipe — matches
        // `MonetStudio.settlePainting`'s "an interrupted reveal comes back
        // finished, not resumed" contract, which is exactly what the
        // reducer already did to `StudioState.painting` the instant this
        // load was triggered.
        if let plan, let sink {
            _ = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: plan.totalMs, sink: sink)
            staticImage = finalImageForPlayback ?? sink.context.makeImage() ?? staticImage
        }
        plan = nil
        sink = nil
        cursor = RevealCursor()
        playbackStartedAt = nil
        playingAssetBase = nil
        finalImageForPlayback = nil
        lastRevealImage = nil

        Task { [weak self, assetClient] in
            guard let self else { return }
            do {
                if let base {
                    let url = PaintingAssetURL.paintingAssetUrl(apiBase: apiBaseURL.absoluteString, ref: base, file: Self.finalFile)
                    let data = try await assetClient.imageData(at: url)
                    let image = try PaintingImageDecoder.decode(data)
                    guard self.generation == gen else { return }
                    self.staticImage = image
                } else {
                    guard self.generation == gen else { return }
                    self.staticImage = nil
                }
            } catch {
                // Base image failed to load: leave whatever was on screen
                // before (matches RasterRevealLayer.tsx's `console.warn` +
                // continue rather than blank the canvas over a transient
                // network hiccup).
            }

            guard let playing, self.generation == gen else { return }
            await self.play(playing, apiBaseURL: apiBaseURL, generation: gen, onPlaybackDone: onPlaybackDone)
        }
    }

    private func play(
        _ ref: PaintingVersionRef,
        apiBaseURL: URL,
        generation gen: Int,
        onPlaybackDone: @escaping (String) -> Void
    ) async {
        do {
            let manifestURL = PaintingAssetURL.paintingAssetUrl(apiBase: apiBaseURL.absoluteString, ref: ref, file: Self.manifestFile)
            let manifest = try await assetClient.manifest(at: manifestURL)
            let builtPlan = buildRevealPlan(manifest)

            var keyframeImages: [CGImage] = []
            keyframeImages.reserveCapacity(manifest.keyframes.count)
            for keyframe in manifest.keyframes {
                let url = PaintingAssetURL.paintingAssetUrl(apiBase: apiBaseURL.absoluteString, ref: ref, file: keyframe.image)
                let data = try await assetClient.imageData(at: url)
                keyframeImages.append(try PaintingImageDecoder.decode(data))
            }
            let finalImage = await Self.loadFinalImage(ref, apiBaseURL: apiBaseURL, assetClient: assetClient)

            guard self.generation == gen else { return }
            let newSink = try RasterRevealSink(plan: builtPlan, images: keyframeImages)
            plan = builtPlan
            sink = newSink
            cursor = RevealCursor()
            playbackStartedAt = Date()
            playingAssetBase = ref.assetBase
            finalImageForPlayback = finalImage
        } catch {
            // Can't animate this version at all (manifest 404, decode
            // failure, ...): show its final image directly if available and
            // report done immediately, rather than leaving the canvas
            // stuck on the previous version forever (RasterRevealLayer.tsx
            // does the same fallback).
            guard self.generation == gen else { return }
            if let image = await Self.loadFinalImage(ref, apiBaseURL: apiBaseURL, assetClient: assetClient) {
                staticImage = image
            }
            loadedBaseKey = ref.assetBase
            loadedPlayingKey = ""
            onPlaybackDone(ref.assetBase)
        }
    }

    // MARK: - Playback

    /// Tracks whether this tick's `advanceRevealPlan` call actually drew
    /// anything, so the composited `CGImage` is only regenerated (an
    /// O(canvas size) copy) on a tick that changed it — never
    /// unconditionally every frame, matching `IncrementalCanvasCache`'s own
    /// "only the newly appended tail" discipline for the strokes layer.
    private final class DirtyTrackingSink: RevealSink {
        let inner: RasterRevealSink
        private(set) var dirty = false
        init(_ inner: RasterRevealSink) { self.inner = inner }
        func revealOps(kf: Int, from: Int, to: Int) { dirty = true; inner.revealOps(kf: kf, from: from, to: to) }
        func settleKeyframe(_ kf: Int) { dirty = true; inner.settleKeyframe(kf) }
        func wipeArea(kf: Int, op: Int, progress: Double) { dirty = true; inner.wipeArea(kf: kf, op: op, progress: progress) }
    }

    private func advancePlayback(now: Date, onPlaybackDone: @escaping (String) -> Void) {
        guard let plan, let sink, let startedAt = playbackStartedAt, let assetBase = playingAssetBase else { return }
        let elapsedMs = now.timeIntervalSince(startedAt) * 1000
        let tracker = DirtyTrackingSink(sink)
        let done = advanceRevealPlan(plan, cursor: &cursor, elapsedMs: elapsedMs, sink: tracker)
        if tracker.dirty || lastRevealImage == nil {
            lastRevealImage = sink.context.makeImage()
        }
        guard done else { return }

        // Finish: show the pixel-exact final image if we have one (an
        // in-flight reveal's last keyframe is only ever "close" — see
        // `finalImageForPlayback`'s doc comment), predict the store's
        // post-`paintingPlaybackDone` state (`base` becomes this version)
        // so the very next `frame()` call doesn't immediately re-trigger a
        // redundant reload of the image we already have, then clear
        // playback state and report completion.
        staticImage = finalImageForPlayback ?? lastRevealImage
        loadedBaseKey = assetBase
        loadedPlayingKey = ""
        self.plan = nil
        self.sink = nil
        cursor = RevealCursor()
        playbackStartedAt = nil
        playingAssetBase = nil
        finalImageForPlayback = nil
        lastRevealImage = nil
        onPlaybackDone(assetBase)
    }

    private static let manifestFile = "reveal.json"
    private static let finalFile = "final.png"

    private static func loadFinalImage(_ ref: PaintingVersionRef, apiBaseURL: URL, assetClient: PaintingAssetClient) async -> CGImage? {
        let url = PaintingAssetURL.paintingAssetUrl(apiBase: apiBaseURL.absoluteString, ref: ref, file: finalFile)
        guard let data = try? await assetClient.imageData(at: url) else { return nil }
        return try? PaintingImageDecoder.decode(data)
    }
}
