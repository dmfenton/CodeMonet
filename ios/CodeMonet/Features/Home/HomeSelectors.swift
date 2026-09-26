import MonetProtocol
import MonetStudio

/// What Home's "on the easel" row shows for the live piece.
struct EaselModel: Equatable {
    enum Preview: Equatable {
        /// A program painting: show this version's `preview.jpg`.
        case painting(PaintingVersionRef)
        /// Vector strokes (plotter, or paint before program painting).
        case strokes([Path], styleConfig: DrawingStyleConfig)
        /// Started, nothing on the canvas yet.
        case blank
    }

    var title: String
    var statusLine: String
    /// The agent is working right now ("Watch") vs. paused/idle ("Continue").
    var isActive: Bool
    var preview: Preview
    var canvasWidth: Int
    var canvasHeight: Int
}

/// Pure derivations for `HomeView`, unit-testable against plain
/// `StudioState` values without a live store or socket.
enum HomeSelectors {
    static let recentLimit = 3

    /// The live piece, or `nil` when no piece has been started yet. A started
    /// but still-blank piece (e.g. Surprise me, paused) stays on the easel so
    /// it can be resumed.
    static func easel(_ state: StudioState) -> EaselModel? {
        let latestPainting = state.painting.playing ?? state.painting.base
        let preview: EaselModel.Preview
        if let latestPainting {
            preview = .painting(latestPainting)
        } else if !state.strokes.isEmpty {
            preview = .strokes(state.strokes, styleConfig: state.styleConfig)
        } else if state.pieceNumber > 0 || state.prompt != nil || state.title != nil {
            preview = .blank
        } else {
            return nil
        }
        let pill = StudioPresentation.statusPill(for: state)
        return EaselModel(
            title: PieceTitle.resolve(title: state.title, prompt: state.prompt, pieceNumber: state.pieceNumber),
            statusLine: StudioPresentation.easelStatusLine(for: state),
            isActive: pill.isActive,
            preview: preview,
            canvasWidth: state.canvasWidth,
            canvasHeight: state.canvasHeight
        )
    }

    /// The newest saved pieces, newest first.
    static func recentPieces(_ state: StudioState) -> [GalleryEntry] {
        Array(GalleryFormatting.newestFirst(state.gallery).prefix(recentLimit))
    }

    /// Begin gating: non-whitespace text and a connected socket.
    static func canSubmit(prompt: String, connected: Bool) -> Bool {
        connected && !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}
