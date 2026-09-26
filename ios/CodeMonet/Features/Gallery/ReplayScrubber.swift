import FentonDesignSystem
import MonetNetworking
import SwiftUI

/// Version-by-version replay control: play/pause, a track with one tick per
/// version (tap or drag to jump), and "replay · v2 of 4".
struct ReplayScrubber: View {
    let versionCount: Int
    /// `nil` = not replaying (the final image is shown).
    let selectedIndex: Int?
    let isPlaying: Bool
    let onSelect: (Int) -> Void
    let onTogglePlay: () -> Void

    var body: some View {
        PaletteReader { palette in
            HStack(spacing: 10) {
                Button(action: onTogglePlay) {
                    Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(palette.surface)
                        .frame(width: 30, height: 30)
                        .background(Circle().fill(palette.accent))
                }
                .accessibilityLabel(isPlaying ? "Pause replay" : "Replay versions")
                .accessibilityIdentifier("piece-replay-play")

                track(palette: palette)
                    .frame(height: 30)

                Text(label)
                    .font(MonetType.meta)
                    .foregroundStyle(palette.tertiaryText)
                    .monospacedDigit()
                    .fixedSize()
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("piece-replay")
        }
    }

    private var label: String {
        guard let selectedIndex else { return "\(versionCount) version\(versionCount == 1 ? "" : "s")" }
        return "v\(selectedIndex + 1) of \(versionCount)"
    }

    private func fraction(for index: Int) -> CGFloat {
        versionCount > 1 ? CGFloat(index) / CGFloat(versionCount - 1) : 1
    }

    private func track(palette: FentonTheme.Palette) -> some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let filled = fraction(for: selectedIndex ?? versionCount - 1) * width
            ZStack(alignment: .leading) {
                Capsule().fill(palette.divider).frame(height: 4)
                Capsule().fill(palette.accent).frame(width: max(4, filled), height: 4)
                ForEach(0 ..< versionCount, id: \.self) { index in
                    let isSelected = index == selectedIndex
                    Circle()
                        .fill(index <= (selectedIndex ?? versionCount - 1) ? palette.accent : palette.divider)
                        .overlay(Circle().strokeBorder(palette.surface, lineWidth: 2))
                        .frame(width: isSelected ? 14 : 10, height: isSelected ? 14 : 10)
                        .position(x: fraction(for: index) * width, y: proxy.size.height / 2)
                }
            }
            .frame(maxHeight: .infinity)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0).onChanged { value in
                    guard width > 0, versionCount > 0 else { return }
                    let raw = value.location.x / width * CGFloat(max(versionCount - 1, 0))
                    let index = min(max(Int(raw.rounded()), 0), versionCount - 1)
                    if index != selectedIndex { onSelect(index) }
                }
            )
        }
        .padding(.horizontal, 7)
        .accessibilityElement()
        .accessibilityLabel("Version")
        .accessibilityValue(label)
        .accessibilityAdjustableAction { direction in
            let current = selectedIndex ?? versionCount - 1
            switch direction {
            case .increment: onSelect(min(current + 1, versionCount - 1))
            case .decrement: onSelect(max(current - 1, 0))
            @unknown default: break
            }
        }
        .sensoryFeedback(.selection, trigger: selectedIndex)
    }
}

/// A version's `painting.py`, fetched from its capability URL and shown in a
/// monospaced, selectable sheet.
struct ProgramSheet: View {
    let title: String
    let urlString: String

    @Environment(\.dismiss) private var dismiss
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @State private var program: String?
    @State private var failed = false

    var body: some View {
        PaletteReader { palette in
            NavigationStack {
                Group {
                    if let program {
                        ScrollView([.vertical, .horizontal]) {
                            Text(program)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(palette.text)
                                .textSelection(.enabled)
                                .padding(FentonSpacing.medium)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .accessibilityIdentifier("program-text")
                    } else if failed {
                        FentonEmptyState(
                            symbol: "doc.text.magnifyingglass",
                            title: "Program unavailable",
                            message: "This version's program isn't available from the server."
                        )
                    } else {
                        ProgressView().tint(palette.accent)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(palette.subtleSurface.ignoresSafeArea())
                .navigationTitle(title)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
            }
            .tint(palette.accent)
            .modifier(AdaptiveSheetPresentation(isRegularWidth: horizontalSizeClass == .regular))
            .task(id: urlString) {
                do {
                    program = try await PaintingAssetClient().text(at: urlString)
                } catch {
                    failed = true
                }
            }
        }
    }
}
