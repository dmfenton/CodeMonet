import SwiftUI

/// Home screen (ux spec §5). Functioning-but-simplified placeholder — the
/// "Start Drawing" prompt input + style picker + Surprise Me, without the
/// Continue-card / recent-work section yet. Owned by the home+gallery+
/// new-canvas UI work package; contract other code depends on is that this
/// view only reads `AppEnvironment` (navigation, studio) and never reaches
/// into `MonetStudio`/`MonetNetworking` types directly.
struct HomeView: View {
    @Environment(AppEnvironment.self) private var environment
    @State private var prompt = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Start Drawing")
                    .font(.headline)

                HStack {
                    TextField("Describe your next piece…", text: $prompt)
                        .accessibilityIdentifier("home-prompt-input")
                    Button {
                        startWithPrompt()
                    } label: {
                        Image(systemName: "arrow.forward.circle.fill")
                    }
                    .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("home-prompt-submit")
                }

                Button {
                    startSurpriseMe()
                } label: {
                    Label("Surprise Me", systemImage: "sparkles")
                        .frame(maxWidth: .infinity)
                }
                .accessibilityIdentifier("home-surprise-me")

                Button {
                    environment.navigation.openGallery(from: .home)
                } label: {
                    Label("View Gallery", systemImage: "photo.on.rectangle")
                }
                .accessibilityIdentifier("home-gallery")
            }
            .padding(16)
        }
        .accessibilityIdentifier("home-panel")
    }

    private func startWithPrompt() {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        prompt = ""
        environment.studio.send(.newCanvas(direction: trimmed.isEmpty ? nil : trimmed, drawingStyle: nil, canvasWidth: nil, canvasHeight: nil))
        environment.navigation.screen = .studio
    }

    private func startSurpriseMe() {
        environment.studio.send(.newCanvas(direction: nil, drawingStyle: nil, canvasWidth: nil, canvasHeight: nil))
        environment.navigation.screen = .studio
    }
}
