import FentonDesignSystem
import MonetProtocol
import MonetStudio
import SwiftUI

/// The painter's notebook: thinking as serif prose, tool calls as compact
/// monospaced lines, critiques and the user's nudges as ruled blocks, each
/// grouped under the version it works toward.
struct NotebookView: View {
    let entries: [NotebookEntry]
    /// Show version separators (paint mode — plotter has no versions).
    let showsVersions: Bool
    /// Stroke count for a produced version, when known.
    let strokes: (Int) -> Int?
    /// Asks for a version's manifest so its stroke count can be shown.
    let requestStrokes: (Int) -> Void

    @State private var followsBottom = true

    var body: some View {
        PaletteReader { palette in
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        SectionLabel("notebook")
                        if entries.isEmpty {
                            Text("The painter's notes will appear here as it works.")
                                .font(MonetType.proseItalic)
                                .foregroundStyle(palette.tertiaryText)
                        }
                        ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                            if showsVersions, let version = entry.version,
                               index == 0 || entries[index - 1].version != version {
                                versionMarker(version, palette: palette)
                            }
                            row(entry, palette: palette)
                                .id(entry.id)
                        }
                        Color.clear.frame(height: 1).id(Self.bottomID)
                    }
                    .padding(.horizontal, 18)
                    .padding(.vertical, FentonSpacing.small)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: scrollKey) {
                    guard followsBottom else { return }
                    withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
                }
                .onAppear { proxy.scrollTo(Self.bottomID, anchor: .bottom) }
                .modifier(TracksBottom(atBottom: $followsBottom))
            }
            .accessibilityIdentifier("studio-notebook")
        }
    }

    private static let bottomID = "notebook-bottom"

    /// Changes whenever the notebook grows (new entry or longer live thought).
    private var scrollKey: String {
        guard let last = entries.last else { return "" }
        if case let .thought(text) = last.kind { return "\(entries.count)-\(text.count)" }
        return "\(entries.count)-\(last.id)"
    }

    private func versionMarker(_ version: Int, palette: FentonTheme.Palette) -> some View {
        HStack(spacing: 8) {
            Text("toward v\(version)")
                .font(MonetType.label)
                .foregroundStyle(palette.tertiaryText)
            Rectangle().fill(palette.divider).frame(height: 1)
        }
        .padding(.top, 4)
        .accessibilityLabel("Work toward version \(version)")
    }

    @ViewBuilder
    private func row(_ entry: NotebookEntry, palette: FentonTheme.Palette) -> some View {
        switch entry.kind {
        case let .thought(text):
            (Text(markdown(text)) + Text(entry.isLive ? " ▍" : "").foregroundStyle(palette.tertiaryText))
                .font(MonetType.prose)
                .foregroundStyle(palette.text)
                .lineSpacing(3)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        case let .tool(call):
            toolLine(call, palette: palette)
        case let .critique(text):
            RuledBlock(label: "critique", text: text, color: palette.emphasis, collapsible: true)
        case let .nudge(text):
            RuledBlock(label: "you", text: text, color: palette.accent)
        case let .error(message, detail):
            RuledBlock(label: "error", text: [message, detail].compactMap { $0 }.joined(separator: "\n"),
                       color: CodeMonetDesignSystem.Extra.error, collapsible: true)
        case let .pieceComplete(number):
            Label(number.map { "piece \($0) complete" } ?? "piece complete", systemImage: "checkmark.seal")
                .font(MonetType.meta)
                .foregroundStyle(palette.success)
        }
    }

    private func toolLine(_ call: NotebookToolCall, palette: FentonTheme.Palette) -> some View {
        let count = call.producedVersion.flatMap(strokes)
        return HStack(spacing: 6) {
            Text("›")
            Text(StudioPresentation.toolLine(call, strokes: count))
                .lineLimit(1)
            if call.inProgress {
                ProgressView().controlSize(.mini).tint(palette.tertiaryText)
            }
            Spacer(minLength: 0)
        }
        .font(MonetType.meta)
        .foregroundStyle(call.failed ? CodeMonetDesignSystem.Extra.error : palette.tertiaryText)
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(RoundedRectangle(cornerRadius: 6, style: .continuous).fill(palette.subtleSurface))
        .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).strokeBorder(palette.divider, lineWidth: 1))
        .task(id: call.producedVersion) {
            if let version = call.producedVersion, count == nil { requestStrokes(version) }
        }
    }
}

/// Keeps `atBottom` current so the notebook only auto-scrolls while the
/// reader is already at the end (iOS 18+; on 17 it always follows).
private struct TracksBottom: ViewModifier {
    @Binding var atBottom: Bool

    private struct Position: Equatable {
        var distanceFromBottom: CGFloat
        var contentHeight: CGFloat
    }

    func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content.onScrollGeometryChange(for: Position.self) { geometry in
                Position(
                    distanceFromBottom: geometry.contentSize.height - geometry.contentOffset.y - geometry.containerSize.height,
                    contentHeight: geometry.contentSize.height
                )
            } action: { old, new in
                // Growth (a new entry) moves the bottom away without the
                // reader scrolling; only a scroll at a stable size decides.
                guard old.contentHeight == new.contentHeight else { return }
                atBottom = new.distanceFromBottom < 60
            }
        } else {
            content
        }
    }
}

/// Inline Markdown (the agent writes `**bold**` in critiques and thoughts),
/// falling back to the raw text if it doesn't parse.
private func markdown(_ text: String) -> AttributedString {
    (try? AttributedString(
        markdown: text,
        options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
    )) ?? AttributedString(text)
}

/// A left-ruled block with a small monospaced label (critique, you, error).
private struct RuledBlock: View {
    let label: String
    let text: String
    let color: Color
    var collapsible = false

    @State private var expanded = false
    private static let collapsedLines = 6

    var body: some View {
        PaletteReader { palette in
            VStack(alignment: .leading, spacing: 3) {
                Text(label)
                    .font(MonetType.label)
                    .foregroundStyle(color)
                Text(markdown(text))
                    .font(MonetType.proseItalic)
                    .foregroundStyle(palette.secondaryText)
                    .lineLimit(collapsible && !expanded ? Self.collapsedLines : nil)
                    .lineSpacing(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.leading, 10)
            .overlay(alignment: .leading) {
                Rectangle().fill(color).frame(width: 2)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                guard collapsible else { return }
                withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
            }
            .accessibilityElement(children: .combine)
        }
    }
}
