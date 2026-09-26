import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// Gallery: a large serif title with the piece count, style filter chips,
/// the latest piece hung large, then a two-column grid (adaptive on iPad).
/// Every piece shows its title and date; tapping one opens its detail.
struct GalleryView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    @State private var filter: GalleryFilter = .all
    @State private var path: [Int] = []
    @State private var refreshError: String?

    private var allEntries: [GalleryEntry] {
        GalleryFormatting.newestFirst(environment.studio.state.gallery)
    }

    private var entries: [GalleryEntry] {
        allEntries.filter(filter.includes)
    }

    private var columns: [GridItem] {
        if horizontalSizeClass == .regular {
            return [GridItem(.adaptive(minimum: 220), spacing: FentonSpacing.medium)]
        }
        return Array(repeating: GridItem(.flexible(), spacing: 14), count: 2)
    }

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    header(palette: palette)
                    if allEntries.isEmpty {
                        emptyOrError
                            .frame(minHeight: 320)
                    } else {
                        filterChips
                            .padding(.top, 12)
                        pieces(palette: palette)
                            .padding(.top, FentonSpacing.medium)
                    }
                }
                .padding(.horizontal, 18)
                .padding(.bottom, FentonSpacing.large)
                .frame(maxWidth: 900)
                .frame(maxWidth: .infinity)
            }
            .refreshable { await refresh() }
            .background(palette.surface.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: Int.self) { pieceNumber in
                if let entry = allEntries.first(where: { $0.pieceNumber == pieceNumber }) {
                    GalleryPieceDetailView(entry: entry)
                }
            }
        }
        .task {
            if let focus = environment.navigation.galleryFocusPiece {
                environment.navigation.galleryFocusPiece = nil
                path = [focus]
            }
            await refresh()
        }
    }

    // MARK: - Header

    private func header(palette: FentonTheme.Palette) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Button {
                    environment.navigation.closeGallery()
                } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(palette.secondaryText)
                        .frame(width: 32, height: 32, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel("Back")
                .accessibilityIdentifier("gallery-close-button")
                Spacer()
                if environment.navigation.galleryOpenedFrom == .studio {
                    Button(action: goHome) {
                        Image(systemName: "house")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundStyle(palette.secondaryText)
                            .frame(width: 32, height: 32)
                    }
                    .accessibilityLabel("Home")
                    .accessibilityIdentifier("gallery-home-button")
                }
            }
            Text("Gallery")
                .font(MonetType.screenTitle)
                .foregroundStyle(palette.text)
                .accessibilityAddTraits(.isHeader)
            if !allEntries.isEmpty {
                Text(GalleryFormatting.summaryLine(for: allEntries))
                    .font(MonetType.meta)
                    .foregroundStyle(palette.tertiaryText)
            }
        }
        .padding(.top, FentonSpacing.small)
    }

    private var filterChips: some View {
        HStack(spacing: 6) {
            ForEach(GalleryFilter.allCases) { candidate in
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { filter = candidate }
                } label: {
                    ChipLabel(text: candidate.label, selected: filter == candidate)
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(filter == candidate ? .isSelected : [])
                .accessibilityIdentifier("gallery-filter-\(candidate.rawValue)")
            }
        }
        .sensoryFeedback(.selection, trigger: filter)
    }

    // MARK: - Pieces

    @ViewBuilder
    private func pieces(palette: FentonTheme.Palette) -> some View {
        if let featured = entries.first {
            VStack(alignment: .leading, spacing: 22) {
                NavigationLink(value: featured.pieceNumber) {
                    GalleryItemView(entry: featured, featured: true)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("gallery-item-\(featured.pieceNumber)")

                LazyVGrid(columns: columns, alignment: .leading, spacing: 18) {
                    ForEach(entries.dropFirst()) { entry in
                        NavigationLink(value: entry.pieceNumber) {
                            GalleryItemView(entry: entry, featured: false)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("gallery-item-\(entry.pieceNumber)")
                    }
                }
            }
        } else {
            Text("No \(filter.label.lowercased()) pieces yet.")
                .font(MonetType.proseItalic)
                .foregroundStyle(palette.tertiaryText)
                .padding(.top, FentonSpacing.large)
        }
    }

    @ViewBuilder
    private var emptyOrError: some View {
        if let refreshError {
            FentonEmptyState(symbol: "exclamationmark.triangle", title: "Couldn't load gallery", message: refreshError)
        } else {
            FentonEmptyState(
                symbol: "photo.on.rectangle",
                title: "No finished pieces yet",
                message: "Start one from Home — it lands here when the painter moves on."
            )
        }
    }

    // MARK: - Actions

    /// Gallery -> Home: pause if running, restore the live canvas if a piece
    /// was being viewed, then land on Home (ux spec §1.1).
    private func goHome() {
        if !environment.studio.state.paused {
            environment.studio.setPausedLocally(true)
            environment.studio.send(.pause)
        }
        environment.studio.clearViewing()
        environment.navigation.screen = .home
    }

    private func refresh() async {
        do {
            environment.studio.applyFetchedGallery(try await environment.restClient.gallery())
            refreshError = nil
        } catch {
            // Keep what we have; only show the error when there's nothing else.
            if allEntries.isEmpty {
                refreshError = "Check your connection and try again."
            }
        }
    }
}

/// One gallery piece: thumbnail in a paper mat, serif-italic title, and a
/// monospaced date.
private struct GalleryItemView: View {
    let entry: GalleryEntry
    let featured: Bool

    var body: some View {
        PaletteReader { palette in
            VStack(alignment: .leading, spacing: featured ? 8 : 6) {
                AuthenticatedThumbnailView(token: entry.thumbnailToken, fallbackSymbol: "photo", contentMode: .fit)
                    .aspectRatio(CGFloat(entry.width) / CGFloat(max(entry.height, 1)), contentMode: .fit)
                    .frame(maxWidth: .infinity)
                    .paperMat(padding: featured ? 8 : 5)
                if featured {
                    HStack(alignment: .firstTextBaseline) {
                        title(palette: palette)
                        Spacer()
                        date(palette: palette)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 1) {
                        title(palette: palette)
                        date(palette: palette)
                    }
                }
            }
            .contentShape(Rectangle())
        }
    }

    private func title(palette: FentonTheme.Palette) -> some View {
        Text(GalleryFormatting.title(for: entry))
            .font(featured ? MonetType.pieceTitle : MonetType.pieceTitleSmall)
            .foregroundStyle(palette.text)
            .lineLimit(featured ? 2 : 1)
    }

    private func date(palette: FentonTheme.Palette) -> some View {
        Text(GalleryFormatting.shortDate(entry.createdAt))
            .font(MonetType.meta)
            .foregroundStyle(palette.tertiaryText)
    }
}
