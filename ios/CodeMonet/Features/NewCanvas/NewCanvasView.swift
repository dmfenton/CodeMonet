import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// New Canvas sheet (ux spec §7.2) — the richer "start a canvas" flow with
/// direction suggestions + style + canvas-size selection. No control in the
/// RN app ever opened this modal; here it's a real, reachable sheet from
/// Home's header (a deliberate native-improvement divergence, per the ux
/// spec's note — approved rather than silently guessed at). Presented with
/// detents + a drag indicator (native improvement #1) instead of a fake
/// bottom sheet.
struct NewCanvasView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    @State private var direction = ""
    @State private var style: DrawingStyleType
    @State private var profile = CanvasSizeProfiles.standard

    /// Pre-seeded from Home's currently-selected style, reset every time the
    /// sheet opens (ux spec §7.2) — automatic here since SwiftUI creates a
    /// fresh `@State` for each new sheet presentation.
    init(initialStyle: DrawingStyleType) {
        _style = State(initialValue: initialStyle)
    }

    private static let suggestions = [
        "A serene landscape", "Abstract shapes", "Something playful",
        "Geometric patterns", "Flowing curves", "Bold and dramatic",
    ]
    private static let maxLength = 200

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: FentonSpacing.large) {
                    suggestionChips(palette: palette)

                    StylePickerView(label: "Style", selection: $style, variant: .pills, testIDPrefix: "new-canvas-style")
                        .onChange(of: style) { _, newValue in
                            // Persist immediately (RN's `handleStyleChange` dispatches on
                            // selection, not on submit) so the choice survives even if the
                            // sheet is dismissed without starting a canvas.
                            environment.studio.setStyle(newValue)
                        }

                    sizeProfileChips(palette: palette)

                    directionInput(palette: palette)
                }
                .padding(FentonSpacing.large)
            }
            .navigationTitle("New Canvas")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .accessibilityLabel("Close")
                }
            }
            .safeAreaInset(edge: .bottom) {
                actions(palette: palette, connected: environment.studio.connected)
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    var subtitle: String { "Give the agent a direction, or let it decide" }

    @ViewBuilder
    private func suggestionChips(palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .leading, spacing: FentonSpacing.extraSmall) {
            Text(subtitle)
                .font(FentonTypography.caption)
                .foregroundStyle(palette.secondaryText)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: FentonSpacing.small) {
                    ForEach(Self.suggestions, id: \.self) { suggestion in
                        Button {
                            direction = suggestion
                        } label: {
                            Text(suggestion)
                                .font(FentonTypography.caption)
                                .foregroundStyle(palette.secondaryText)
                                .padding(.horizontal, FentonSpacing.medium)
                                .padding(.vertical, FentonSpacing.small)
                                .background(Capsule().fill(palette.subtleSurface))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func sizeProfileChips(palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .leading, spacing: FentonSpacing.small) {
            Text("Canvas Size")
                .font(FentonTypography.label)
                .foregroundStyle(palette.tertiaryText)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: FentonSpacing.small) {
                    ForEach(CanvasSizeProfiles.all) { candidate in
                        let selected = candidate == profile
                        Button {
                            profile = candidate
                        } label: {
                            Text(candidate.label)
                                .font(FentonTypography.caption.weight(.semibold))
                                .foregroundStyle(selected ? .white : palette.secondaryText)
                                .padding(.horizontal, FentonSpacing.medium)
                                .padding(.vertical, FentonSpacing.small)
                                .background(Capsule().fill(selected ? palette.accent : palette.subtleSurface))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("new-canvas-size-\(candidate.id)-button")
                    }
                }
            }
            .sensoryFeedback(.selection, trigger: profile)
        }
    }

    @ViewBuilder
    private func directionInput(palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .trailing, spacing: FentonSpacing.extraSmall) {
            TextField("Describe what to draw...", text: $direction, axis: .vertical)
                .lineLimit(4...8)
                .padding(FentonSpacing.medium)
                .background(
                    RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous)
                        .fill(palette.subtleSurface)
                )
                .onChange(of: direction) { _, newValue in
                    if newValue.count > Self.maxLength { direction = String(newValue.prefix(Self.maxLength)) }
                }
                .accessibilityIdentifier("new-canvas-input")

            let remaining = Self.maxLength - direction.count
            Text("\(remaining)")
                .font(FentonTypography.caption)
                .foregroundStyle(remaining < 20 ? palette.warning : palette.tertiaryText)
        }
    }

    @ViewBuilder
    private func actions(palette: FentonTheme.Palette, connected: Bool) -> some View {
        let hasText = !direction.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let startEnabled = connected && hasText
        HStack(spacing: FentonSpacing.medium) {
            Button {
                start(withDirection: false)
            } label: {
                Text("Let Agent Decide")
                    .font(.system(.body, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, FentonSpacing.medium)
                    .foregroundStyle(palette.secondaryText)
                    .background(
                        RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous)
                            .fill(palette.subtleSurface)
                    )
            }
            .buttonStyle(.plain)
            .disabled(!connected)
            .opacity(connected ? 1 : 0.5)

            Button {
                start(withDirection: true)
            } label: {
                Label("Start", systemImage: "paintbrush.fill")
                    .font(.system(.body, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, FentonSpacing.medium)
                    .foregroundStyle(startEnabled ? .white : palette.tertiaryText)
                    .background(
                        RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous)
                            .fill(startEnabled ? palette.accent : palette.subtleSurface)
                    )
            }
            .buttonStyle(.plain)
            .disabled(!connected)
            .accessibilityIdentifier("new-canvas-start-button")
        }
        .padding(FentonSpacing.large)
        .background(.bar)
    }

    /// "Let Agent Decide" always starts with no direction, even if text was
    /// typed (ux spec §7.2's "Skip" path); "Start" uses the trimmed text, or
    /// no direction if it's empty — the two paths look different but behave
    /// identically when the field is empty.
    private func start(withDirection: Bool) {
        let trimmed = direction.trimmingCharacters(in: .whitespacesAndNewlines)
        environment.studio.send(.newCanvas(
            direction: withDirection && !trimmed.isEmpty ? trimmed : nil,
            drawingStyle: style,
            canvasWidth: profile.width,
            canvasHeight: profile.height
        ))
        environment.studio.send(.resume(direction: nil))
        environment.navigation.screen = .studio
        dismiss()
    }
}
