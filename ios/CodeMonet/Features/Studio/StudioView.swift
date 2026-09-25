import MonetStudio
import SwiftUI

/// Studio screen (ux spec §6): LiveStatus, Canvas, MessageStream, ActionBar.
/// Functioning-but-simplified placeholder — real LiveStatus/MessageStream
/// presentation is the studio-UI work package's job; the contract other
/// code depends on is that this view drives `StudioStore` only through its
/// public methods (`send`, `startPlayback`/`stopPlayback`), never by poking
/// `StudioState` directly.
struct StudioView: View {
    @Environment(AppEnvironment.self) private var environment

    var body: some View {
        VStack(spacing: 12) {
            let status = StudioSelectors.agentStatus(environment.studio.state)
            if status != .idle {
                Text(statusLabel(status))
                    .font(.subheadline)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Color(uiColor: .secondarySystemBackground)))
                    .accessibilityIdentifier("live-status")
            }

            CanvasView()

            actionBar
        }
        .padding(16)
        .accessibilityIdentifier("action-bar")
        .onAppear { environment.studio.startPlayback() }
        .onDisappear { environment.studio.stopPlayback() }
    }

    @ViewBuilder
    private var actionBar: some View {
        HStack {
            Button {
                goHome()
            } label: {
                Label("Home", systemImage: "house")
            }
            .accessibilityIdentifier("action-home")

            Spacer()

            Button {
                environment.navigation.openGallery(from: .studio)
            } label: {
                Label("Gallery", systemImage: "photo.on.rectangle")
            }
            .accessibilityIdentifier("action-gallery")

            Spacer()

            Button {
                togglePause()
            } label: {
                Label(environment.studio.state.paused ? "Start" : "Pause", systemImage: environment.studio.state.paused ? "play" : "pause")
            }
            .accessibilityIdentifier("action-pause")
        }
    }

    private func statusLabel(_ status: AgentStatus) -> String {
        switch status {
        case .idle: "Idle"
        case .thinking: "Thinking…"
        case .executing: "Running code…"
        case .drawing: "Drawing…"
        case .paused: "Paused"
        case .error: "Error"
        }
    }

    private func togglePause() {
        if environment.studio.state.paused {
            environment.studio.send(.resume(direction: nil))
        } else {
            environment.studio.send(.pause)
        }
    }

    private func goHome() {
        if !environment.studio.state.paused {
            environment.studio.send(.pause)
        }
        environment.navigation.screen = .home
    }
}
