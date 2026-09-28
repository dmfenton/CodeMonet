import MonetProtocol

/// Program-painting playback state (docs/program-painting.md "Live
/// performance", mirrors `shared/src/canvas/reducer.ts` `PaintingState`):
///
/// - `base` is fully shown (its `final.png`), or `nil` for a blank canvas;
/// - `playing` is a recorded version whose `performance.bin` plays over
///   `base` (a version this client did not watch live, e.g. after a
///   reconnect);
/// - `live` is a paint run streaming its performance over `base` right now.
///
/// All `nil` means "blank canvas, no painting yet."
public struct PaintingState: Equatable, Sendable {
    public var base: PaintingVersionRef?
    public var playing: PaintingVersionRef?
    public var live: LivePainting?

    public init(base: PaintingVersionRef? = nil, playing: PaintingVersionRef? = nil, live: LivePainting? = nil) {
        self.base = base
        self.playing = playing
        self.live = live
    }
}

/// A live paint run, from its first streamed stroke until it settles into
/// `PaintingState.base`.
public struct LivePainting: Equatable, Sendable {
    public var ref: PaintingLiveRef
    /// The recorded version, once the server confirms the run succeeded
    /// (`painting_version` with the same `asset_base`).
    public var confirmed: PaintingVersionRef?
    /// Playback reached the end of the stream (waiting only on confirmation).
    public var played: Bool

    public init(ref: PaintingLiveRef, confirmed: PaintingVersionRef? = nil, played: Bool = false) {
        self.ref = ref
        self.confirmed = confirmed
        self.played = played
    }
}

/// Collapses any in-flight playback to its final image: a confirmed live run
/// or a playing version becomes the base; an unconfirmed live run is
/// dropped. Used when a new version/run supersedes the current one and when
/// gallery view is entered (the interrupted playback comes back finished,
/// not resumed).
public func settlePainting(_ state: PaintingState) -> PaintingState {
    PaintingState(base: state.live?.confirmed ?? state.playing ?? state.base)
}

/// `true` iff there is anything to show for program painting at all —
/// drives `AgentStatus`/idle-animation gating in `StudioSelectors`.
public func hasPainting(_ state: PaintingState) -> Bool {
    state.base != nil || state.playing != nil || state.live != nil
}

/// `true` while a performance is (or should be) playing: a recorded version,
/// or a live run whose stream has not played to its end.
public func isPaintingPerforming(_ state: PaintingState) -> Bool {
    if state.playing != nil { return true }
    if let live = state.live { return !live.played }
    return false
}
