import FentonDesignSystem
import MonetProtocol
import MonetStudio
import SwiftUI
import UIKit

/// The painter's passes for one version, filling in as they reveal:
/// finished stages in the accent, the stage being revealed in emphasis,
/// pending stages in the divider color. Widths follow each stage's op count.
/// Each segment carries its label only when every label fits in full
/// (`StageBar.labelsFit`); otherwise one caption sits under the bar
/// (`StageBar.caption`: "stage 4 of 8 · harbor" / "8 stages · final touches").
struct StageBarView: View {
    let segments: [StageSegment]

    private static let spacing: CGFloat = 3

    /// Width of one character of the (monospaced) label font.
    private static var characterWidth: CGFloat {
        let size = UIFont.preferredFont(forTextStyle: .caption2).pointSize
        let font = UIFont.monospacedSystemFont(ofSize: size, weight: .medium)
        return ("0" as NSString).size(withAttributes: [.font: font]).width
    }

    @State private var width: CGFloat = 0

    var body: some View {
        PaletteReader { palette in
            let showsLabels = StageBar.labelsFit(
                segments, totalWidth: Double(width), spacing: Double(Self.spacing), characterWidth: Double(Self.characterWidth)
            )
            VStack(alignment: .leading, spacing: 4) {
                GeometryReader { proxy in
                    let available = max(0, proxy.size.width - Self.spacing * CGFloat(max(segments.count - 1, 0)))
                    HStack(alignment: .top, spacing: Self.spacing) {
                        ForEach(segments) { segment in
                            Capsule()
                                .fill(color(segment.progress, palette: palette))
                                .frame(width: available * segment.fraction, height: 4)
                        }
                    }
                    .onAppear { width = proxy.size.width }
                    .onChange(of: proxy.size.width) { _, newWidth in width = newWidth }
                }
                .frame(height: 4)
                if showsLabels {
                    labels(palette: palette)
                } else {
                    caption(palette: palette)
                }
            }
            .animation(.easeInOut(duration: 0.25), value: segments)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(accessibilityText)
            .accessibilityIdentifier("studio-stage-bar")
        }
    }

    private func labels(palette: FentonTheme.Palette) -> some View {
        let available = max(0, width - Self.spacing * CGFloat(max(segments.count - 1, 0)))
        return HStack(alignment: .top, spacing: Self.spacing) {
            ForEach(segments) { segment in
                Text(segment.label)
                    .font(MonetType.label)
                    .foregroundStyle(segment.progress == .current ? palette.emphasis : palette.tertiaryText)
                    .lineLimit(1)
                    .fixedSize()
                    .frame(width: available * segment.fraction, alignment: .leading)
            }
        }
    }

    private func caption(palette: FentonTheme.Palette) -> some View {
        let caption = StageBar.caption(segments)
        let current = segments.first { $0.progress == .current }
        let lead = current.map { String(caption.dropLast($0.label.count)) } ?? caption
        return (Text(lead).foregroundStyle(palette.tertiaryText)
            + Text(current?.label ?? "").foregroundStyle(palette.emphasis))
            .font(MonetType.label)
            .lineLimit(1)
            .truncationMode(.tail)
            .accessibilityIdentifier("studio-stage-caption")
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
                    .onChange(of: versions.count) {
                        // A new version becomes live (and selected) unless one is pinned.
                        withAnimation { proxy.scrollTo(selected ?? versions.last?.version, anchor: .trailing) }
                    }
                    .onChange(of: selected) { _, newValue in
                        withAnimation { proxy.scrollTo(newValue, anchor: .center) }
                    }
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
