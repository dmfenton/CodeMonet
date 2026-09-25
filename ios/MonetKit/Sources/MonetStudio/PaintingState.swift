import MonetProtocol

/// Program-painting playback state (program-painting spec §4.1
/// `PaintingState`): `base` is fully shown; `playing` is being revealed
/// over it. Both `nil` means "blank canvas, no painting yet."
public struct PaintingState: Equatable, Sendable {
    public var base: PaintingVersionRef?
    public var playing: PaintingVersionRef?

    public init(base: PaintingVersionRef? = nil, playing: PaintingVersionRef? = nil) {
        self.base = base
        self.playing = playing
    }
}

/// Collapses an in-flight `playing` reveal into `base` — used both when a
/// new version supersedes a mid-reveal one (spec §4.1 step 3) and when
/// gallery view is entered/exited mid-reveal (spec §4.1 `LOAD_CANVAS`/
/// `CLEAR_VIEWING`: the interrupted reveal comes back already-finished, not
/// resumed).
public func settlePainting(_ state: PaintingState) -> PaintingState {
    guard let playing = state.playing else { return state }
    return PaintingState(base: playing, playing: nil)
}

/// `true` iff there is anything to show for program painting at all (spec
/// §4.1) — drives `AgentStatus`/idle-animation gating in `StudioSelectors`.
public func hasPainting(_ state: PaintingState) -> Bool {
    state.base != nil || state.playing != nil
}
