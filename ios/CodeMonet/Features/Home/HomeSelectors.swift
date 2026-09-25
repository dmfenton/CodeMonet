import MonetProtocol
import MonetStudio

/// What the Continue card (ux spec §5.2) should render — a discriminated
/// union rather than the RN version's `hasCurrentWork` boolean + nullable
/// `recentCanvas` pair, so every call site is forced to handle exactly one
/// of the three real states instead of re-deriving the combination.
public enum ContinueCardKind: Equatable {
    /// Live work-in-progress: render a WIP stroke preview, tappable, shows
    /// the "Continue" pill.
    case live(strokes: [Path], canvasWidth: Int, canvasHeight: Int, styleConfig: DrawingStyleConfig, title: String)
    /// A completed gallery piece with no live work in progress: render its
    /// authenticated thumbnail, static (non-tappable) card.
    case completed(entry: GalleryEntry)
    /// No recent work at all — the whole OR-divider + Continue section is
    /// hidden (ux spec §5.4).
    case none
}

/// Pure derivations for `HomeView` (ux spec §5), factored out of the view so
/// they're unit-testable against plain `StudioState` fixtures without a
/// live `StudioStore`/socket.
public enum HomeSelectors {
    /// ux spec §5.2: shown when **any** of — live strokes exist, at least
    /// one gallery entry exists, or a session is already active
    /// (`pieceNumber > 0`, even with zero strokes so far).
    public static func hasRecentWork(_ state: StudioState) -> Bool {
        !state.strokes.isEmpty || !state.gallery.isEmpty || state.pieceNumber > 0
    }

    /// "Continue where you left off" when live work exists, else "Recent
    /// work" (ux spec §5.2). Only meaningful when `hasRecentWork` is true.
    public static func continueSectionHeader(_ state: StudioState) -> String {
        hasCurrentWork(state) ? "Continue where you left off" : "Recent work"
    }

    /// ux spec §5.2's `ContinueCard` branch: live preview beats a completed
    /// thumbnail beats nothing. `hasCurrentWork` alone (zero strokes so far)
    /// still counts as "live" for card *identity* (tappable, "Continue"
    /// pill) even though the preview itself only appears once strokes > 0.
    public static func continueCardKind(_ state: StudioState) -> ContinueCardKind {
        guard hasRecentWork(state) else { return .none }
        if hasCurrentWork(state) {
            return .live(
                strokes: state.strokes,
                canvasWidth: state.canvasWidth,
                canvasHeight: state.canvasHeight,
                styleConfig: state.styleConfig,
                title: "Current Drawing"
            )
        }
        if let entry = state.gallery.last {
            return .completed(entry: entry)
        }
        // A session is active (pieceNumber > 0) but neither live strokes nor
        // a gallery entry exist yet — treat as live/resumable (matches RN's
        // `hasCurrentWork` semantics, which don't require strokes.length >
        // 0 to be true, only to show the preview itself).
        return .live(
            strokes: [],
            canvasWidth: state.canvasWidth,
            canvasHeight: state.canvasHeight,
            styleConfig: state.styleConfig,
            title: "Current Drawing"
        )
    }

    /// RN's `hasCurrentWork = canvasState.strokes.length > 0` (App.tsx) —
    /// gates whether the Continue card is tappable/live vs. a static
    /// completed-piece card. Deliberately *not* the same predicate as
    /// `hasRecentWork` above.
    public static func hasCurrentWork(_ state: StudioState) -> Bool {
        !state.strokes.isEmpty
    }

    /// PromptInput/Surprise-Me submit gating (ux spec §5.1): non-whitespace
    /// text (when text is involved) **and** the socket connected.
    public static func canSubmit(prompt: String, connected: Bool) -> Bool {
        connected && !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}
