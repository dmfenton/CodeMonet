import MonetStudio
import SwiftUI

/// Studio screen (ux spec §6): LiveStatus, Canvas, MessageStream, ActionBar,
/// in that vertical order, plus the Nudge sheet. View-only mode
/// (`state.viewingPiece != nil`, ux spec §6 intro) hides LiveStatus and
/// MessageStream entirely and disables drawing/idle-animation/pause-resume —
/// `CanvasView`/`StudioPresentation.actionBarButtons` handle those internal
/// gates; this view only handles the two whole-section hides.
///
/// The ux spec's "Home" button behavior also clears gallery-view mode
/// (`CLEAR_VIEWING`, protocol-state spec §5.4) so the live canvas
/// reappears; `goHome()` does this via `StudioStore.clearViewing()`
/// (added during integration to close a gap this package originally
/// flagged — see `CanvasView.drawingEnabled`'s doc comment for the
/// unrelated, still-open `drawingEnabled` gap).
struct StudioView: View {
    @Environment(AppEnvironment.self) private var environment

    /// View-local "Draw" toggle — see `CanvasView.drawingEnabled`.
    @State private var drawingEnabled = false
    @State private var pieceCompleteHapticTrigger = false
    @State private var pauseHapticTrigger = false
    @State private var drawHapticTrigger = false

    private var state: MonetStudio.StudioState { environment.studio.state }
    private var isViewOnly: Bool { state.viewingPiece != nil }
    private var liveStatusDisplay: StudioPresentation.LiveStatusDisplay? {
        isViewOnly ? nil : StudioPresentation.liveStatus(for: state)
    }

    var body: some View {
        VStack(spacing: 12) {
            if let display = liveStatusDisplay {
                LiveStatusView(display: display)
                    .transition(.opacity)
            }

            CanvasView(drawingEnabled: drawingEnabled)

            if !isViewOnly {
                MessageStreamView(messages: state.messages)
            }

            ActionBarView(buttons: actionBarButtons, onTap: handle(action:))
        }
        .animation(.easeInOut(duration: 0.2), value: liveStatusDisplay != nil)
        .padding(16)
        .onAppear { environment.studio.startPlayback() }
        .onDisappear { environment.studio.stopPlayback() }
        .onChange(of: state.messages.last?.id) {
            guard state.messages.last?.type == .pieceComplete else { return }
            pieceCompleteHapticTrigger.toggle()
        }
        .sensoryFeedback(.success, trigger: pieceCompleteHapticTrigger)
        .sensoryFeedback(.selection, trigger: pauseHapticTrigger)
        .sensoryFeedback(.selection, trigger: drawHapticTrigger)
        .sheet(isPresented: nudgeSheetBinding) {
            NudgeSheetView(onSend: sendNudge, onDismiss: closeNudge)
        }
    }

    private var actionBarButtons: [StudioPresentation.ActionBarButton] {
        StudioPresentation.actionBarButtons(
            paused: state.paused,
            viewOnly: isViewOnly,
            drawingEnabled: drawingEnabled,
            connected: environment.studio.connected,
            galleryCount: state.gallery.count
        )
    }

    private var nudgeSheetBinding: Binding<Bool> {
        Binding(
            get: { environment.navigation.activeModal == .nudge },
            set: { isPresented in
                if !isPresented { environment.navigation.activeModal = nil }
            }
        )
    }

    private func handle(action kind: StudioPresentation.ActionBarButton.Kind) {
        switch kind {
        case .draw:
            drawHapticTrigger.toggle()
            drawingEnabled.toggle()
        case .nudge:
            environment.navigation.activeModal = .nudge
        case .home:
            goHome()
        case .gallery:
            environment.navigation.openGallery(from: .studio)
        case .pause:
            pauseHapticTrigger.toggle()
            togglePause()
        }
    }

    private func togglePause() {
        if state.paused {
            environment.studio.send(.resume(direction: nil))
        } else {
            environment.studio.send(.pause)
        }
    }

    private func goHome() {
        if !state.paused {
            environment.studio.send(.pause)
        }
        drawingEnabled = false
        environment.studio.clearViewing()
        environment.navigation.screen = .home
    }

    private func sendNudge(_ text: String) {
        environment.studio.send(.nudge(text: text))
    }

    private func closeNudge() {
        environment.navigation.activeModal = nil
    }
}
