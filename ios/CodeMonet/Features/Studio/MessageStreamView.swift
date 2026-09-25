import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// Collapsible "Thoughts" history of agent messages (ux spec §6.3).
/// Collapsed by default on every mount — it does not remember open/closed
/// state across screens, matching the RN app's `useState(true)` semantics.
struct MessageStreamView: View {
    let messages: [AgentMessage]

    @State private var collapsed = true
    @State private var autoScroll = true
    @State private var containerHeight: CGFloat?

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    private var palette: FentonTheme.Palette { theme.palette(for: colorScheme) }

    var body: some View {
        VStack(spacing: 0) {
            header
            if !collapsed {
                content
            }
        }
        .background(RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous).fill(palette.elevatedSurface))
        .shadow(color: Color.black.opacity(0.05), radius: 10, x: 0, y: 3)
        .clipShape(RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous))
    }

    private var header: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { collapsed.toggle() }
        } label: {
            HStack(spacing: FentonSpacing.small) {
                Image(systemName: collapsed ? "chevron.forward" : "chevron.down")
                    .font(.system(size: 12))
                    .foregroundStyle(palette.tertiaryText)
                    .accessibilityHidden(true)
                Text("Thoughts")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(palette.text)
                Text("\(messages.count)")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(palette.tertiaryText)
                    .padding(.horizontal, FentonSpacing.small)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(palette.subtleSurface))
                Spacer()
            }
            .padding(.horizontal, FentonSpacing.medium)
            .padding(.vertical, FentonSpacing.small)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Thoughts, \(messages.count) messages, \(collapsed ? "collapsed" : "expanded")")
        .accessibilityAddTraits(.isButton)
    }

    @ViewBuilder
    private var content: some View {
        ScrollViewReader { proxy in
            ZStack(alignment: .bottomTrailing) {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: FentonSpacing.extraSmall) {
                        if messages.isEmpty {
                            emptyState
                        } else {
                            ForEach(messages) { message in
                                MessageBubbleView(message: message)
                                    .id(message.id)
                            }
                        }
                    }
                    .padding(FentonSpacing.small)
                    .background(
                        GeometryReader { geometry in
                            Color.clear.preference(
                                key: MessageStreamBottomOffsetKey.self,
                                value: geometry.frame(in: .named("messageStream")).maxY
                            )
                        }
                    )
                }
                .frame(maxHeight: 280)
                .coordinateSpace(name: "messageStream")
                .background(
                    GeometryReader { geometry in
                        Color.clear.preference(key: MessageStreamHeightKey.self, value: geometry.size.height)
                    }
                )
                .onPreferenceChange(MessageStreamHeightKey.self) { containerHeight = $0 }
                .onPreferenceChange(MessageStreamBottomOffsetKey.self) { bottomOffset in
                    guard let containerHeight else { return }
                    autoScroll = bottomOffset <= containerHeight + 50
                }
                .onChange(of: messages.last?.id) {
                    guard autoScroll, let lastID = messages.last?.id else { return }
                    withAnimation { proxy.scrollTo(lastID, anchor: .bottom) }
                }

                if !autoScroll, !messages.isEmpty {
                    scrollToBottomButton(proxy: proxy)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: FentonSpacing.medium) {
            Image(systemName: "paintpalette")
                .font(.system(size: 32, weight: .light))
                .foregroundStyle(palette.tertiaryText)
                .accessibilityHidden(true)
            Text("No thoughts yet...")
                .font(.caption)
                .foregroundStyle(palette.tertiaryText)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, FentonSpacing.large)
    }

    private func scrollToBottomButton(proxy: ScrollViewProxy) -> some View {
        Button {
            autoScroll = true
            if let lastID = messages.last?.id {
                withAnimation { proxy.scrollTo(lastID, anchor: .bottom) }
            }
        } label: {
            Image(systemName: "arrow.down")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 32, height: 32)
                .background(Circle().fill(palette.accent))
                .accessibilityHidden(true)
        }
        .padding(FentonSpacing.medium)
        .accessibilityLabel("Scroll to bottom")
    }
}

/// Tracks whether the user has scrolled away from the bottom (ux spec §6.3:
/// auto-scroll only while already within 50px of the bottom).
/// `GeometryReader` frame tracking stands in for the RN app's `onScroll`
/// contentOffset math: the content's bottom edge, in the scroll container's
/// coordinate space, equals the container's height exactly when scrolled to
/// the bottom.
private struct MessageStreamBottomOffsetKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

private struct MessageStreamHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}
