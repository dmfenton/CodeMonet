import FentonDesignSystem
import MonetProtocol
import MonetStudio
import SwiftUI

/// The painter's passes for one version, filling in as they reveal:
/// finished stages in the accent, the stage being revealed in emphasis,
/// pending stages in the divider color. Widths follow each stage's op count.
struct StageBarView: View {
    let segments: [StageSegment]

    var body: some View {
        PaletteReader { palette in
            GeometryReader { proxy in
                let spacing: CGFloat = 3
                let available = max(0, proxy.size.width - spacing * CGFloat(max(segments.count - 1, 0)))
                HStack(alignment: .top, spacing: spacing) {
                    ForEach(segments) { segment in
                        VStack(alignment: .leading, spacing: 4) {
                            Capsule()
                                .fill(color(segment.progress, palette: palette))
                                .frame(height: 4)
                            Text(segment.label)
                                .font(MonetType.label)
                                .foregroundStyle(segment.progress == .current ? palette.emphasis : palette.tertiaryText)
                                .lineLimit(1)
                                .truncationMode(.tail)
                        }
                        .frame(width: available * segment.fraction, alignment: .leading)
                    }
                }
            }
            .frame(height: 22)
            .animation(.easeInOut(duration: 0.25), value: segments)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(accessibilityText)
            .accessibilityIdentifier("studio-stage-bar")
        }
    }

    private func color(_ progress: StageSegment.Progress, palette: FentonTheme.Palette) -> Color {
        switch progress {
        case .done: palette.accent
        case .current: palette.emphasis
        case .pending: palette.divider
        }
    }

    private var accessibilityText: String {
        let labels = segments.map(\.label).joined(separator: ", ")
        if let current = segments.first(where: { $0.progress == .current }) {
            return "Stages: \(labels). Painting \(current.label)."
        }
        return "Stages: \(labels)."
    }
}

/// Version chips (v1…vN). Tapping an older version pins its final image
/// over the canvas; the live version (or "Back to live") unpins.
struct VersionChipsView: View {
    let versions: [PaintingVersionSummary]
    let liveVersion: Int?
    let pinnedVersion: Int?
    let onSelect: (Int?) -> Void

    var body: some View {
        PaletteReader { palette in
            HStack(spacing: 6) {
                SectionLabel("versions")
                ScrollViewReader { proxy in
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 5) {
                            Color.clear.frame(width: 4, height: 1)
                            ForEach(versions) { summary in
                                Button {
                                    onSelect(summary.version == liveVersion ? nil : summary.version)
                                } label: {
                                    ChipLabel(text: "v\(summary.version)", selected: summary.version == selected, monospaced: true)
                                }
                                .buttonStyle(.plain)
                                .id(summary.version)
                                .accessibilityLabel("Version \(summary.version)\(summary.version == liveVersion ? ", live" : "")")
                                .accessibilityIdentifier("studio-version-\(summary.version)")
                            }
                        }
                        .padding(.vertical, 1)
                    }
                    .mask(
                        LinearGradient(
                            stops: [.init(color: .clear, location: 0), .init(color: .black, location: 0.06)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .onAppear { proxy.scrollTo(versions.last?.version, anchor: .trailing) }
                    .onChange(of: versions.count) { proxy.scrollTo(versions.last?.version, anchor: .trailing) }
                }
                if pinnedVersion != nil {
                    Button {
                        onSelect(nil)
                    } label: {
                        Label("Back to live", systemImage: "dot.radiowaves.left.and.right")
                            .font(MonetType.chip)
                            .foregroundStyle(palette.accent)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("studio-back-to-live")
                }
            }
        }
    }

    private var selected: Int? { pinnedVersion ?? liveVersion }
}
