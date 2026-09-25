import MonetProtocol
import SwiftUI

/// New Canvas sheet (ux spec §7.2) — the richer "start a canvas" flow with
/// direction + style + size selection. Per the spec, no control in the
/// current RN app actually opens this; keep it as a real, reachable sheet
/// here (a native improvement) rather than porting the unreachable-sheet
/// gap. Functioning-but-simplified placeholder: direction text + style
/// picker only, no size-profile chips yet.
struct NewCanvasView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    @State private var direction = ""
    @State private var style: DrawingStyleType = .plotter

    var body: some View {
        NavigationStack {
            Form {
                Section("Direction") {
                    TextField("Describe what to draw...", text: $direction, axis: .vertical)
                        .accessibilityIdentifier("new-canvas-input")
                }
                Section("Style") {
                    Picker("Style", selection: $style) {
                        Text("Plotter").tag(DrawingStyleType.plotter)
                        Text("Paint").tag(DrawingStyleType.paint)
                    }
                    .pickerStyle(.segmented)
                }
            }
            .navigationTitle("New Canvas")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Start") { start() }
                        .accessibilityIdentifier("new-canvas-start-button")
                }
            }
        }
    }

    private func start() {
        let trimmed = direction.trimmingCharacters(in: .whitespacesAndNewlines)
        environment.studio.send(.newCanvas(
            direction: trimmed.isEmpty ? nil : trimmed,
            drawingStyle: style,
            canvasWidth: nil,
            canvasHeight: nil
        ))
        environment.navigation.screen = .studio
        dismiss()
    }
}
