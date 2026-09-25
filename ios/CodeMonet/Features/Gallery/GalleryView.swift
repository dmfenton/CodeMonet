import FentonDesignSystem
import MonetProtocol
import SwiftUI

/// Gallery grid (ux spec §8): 2-column adaptive grid of authenticated
/// thumbnails (adaptive column count on iPad, native improvement #7), a
/// custom 3-column header (Home button only when opened from Studio, close
/// X always), pull-to-refresh, and empty/error states via
/// `FentonEmptyState` (native improvement #11).
struct GalleryView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    /// Overrides `environment.studio.state.gallery` after a manual
    /// pull-to-refresh, since `StudioStore` has no public API to push a
    /// REST-fetched list back into the reducer-owned state — the server
    /// already pushes `gallery_update` proactively, so this is a
    /// user-triggered "catch me up now" rather than the sole source of
    /// truth.
    @State private var refreshedGallery: [GalleryEntry]?
    @State private var refreshError: String?

    private var entries: [GalleryEntry] {
        (refreshedGallery ?? environment.studio.state.gallery).reversed()
    }

    /// 2 fixed columns on phone (ux spec §8's `NUM_COLUMNS = 2`); adaptive
    /// on iPad (`horizontalSizeClass == .regular`, native improvement #7) so
    /// wider layouts get more columns instead of two oversized cells.
    private var columns: [GridItem] {
        if horizontalSizeClass == .regular {
            return [GridItem(.adaptive(minimum: 200), spacing: FentonSpacing.medium)]
        }
        return Array(repeating: GridItem(.flexible(), spacing: FentonSpacing.medium), count: 2)
    }

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        VStack(spacing: 0) {
            header(palette: palette)

            if entries.isEmpty {
                emptyOrError(palette: palette)
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: FentonSpacing.medium) {
                        ForEach(entries) { entry in
                            GalleryCell(entry: entry) {
                                select(entry)
                            }
                        }
                    }
                    .padding(FentonSpacing.large)
                }
                .refreshable { await refresh() }
            }
        }
        .background(palette.surface)
        .task { await refresh() }
    }

    @ViewBuilder
    private func header(palette: FentonTheme.Palette) -> some View {
        HStack {
            if environment.navigation.galleryOpenedFrom == .studio {
                Button {
                    goHome()
                } label: {
                    Image(systemName: "house")
                }
                .accessibilityIdentifier("gallery-home-button")
                .accessibilityLabel("Home")
            } else {
                Color.clear.frame(width: 22, height: 22)
            }

            Spacer()
            Text("Gallery")
                .font(.system(.title3, weight: .semibold))
            Spacer()

            Button {
                environment.navigation.closeGallery()
            } label: {
                Image(systemName: "xmark")
            }
            .accessibilityIdentifier("gallery-close-button")
            .accessibilityLabel("Close")
        }
        .font(.system(size: 20))
        .foregroundStyle(palette.text)
        .padding(.horizontal, FentonSpacing.large)
        .padding(.vertical, FentonSpacing.medium)
        .overlay(alignment: .bottom) {
            Rectangle().fill(palette.divider).frame(height: 1)
        }
    }

    @ViewBuilder
    private func emptyOrError(palette: FentonTheme.Palette) -> some View {
        if let refreshError {
            FentonEmptyState(
                symbol: "exclamationmark.triangle",
                title: "Couldn't load gallery",
                message: refreshError
            )
        } else {
            FentonEmptyState(
                symbol: "photo.stack",
                title: "No saved artwork yet",
                message: "Finish a piece from Studio and it'll show up here."
            )
        }
    }

    /// ux spec §1.1 "Gallery -> Studio (piece select)" row. Matches RN's
    /// `handleGallerySelect`: a `GET /gallery/{n}/strokes` REST round-trip
    /// (not the WS `load_canvas` message, which has no ack) so a failure is
    /// a definite, catchable event rather than something the client would
    /// otherwise have to guess about with a timeout. Navigates to Studio
    /// optimistically, same as RN; on failure, pauses if running and falls
    /// back to Home instead of leaving the user sitting on a piece that
    /// never loaded — this screen is dismissed by that point (`screen`
    /// switches away from `.gallery`), so, matching RN, the failure is
    /// silent rather than surfaced as a banner here.
    private func select(_ entry: GalleryEntry) {
        environment.navigation.screen = .studio
        Task {
            do {
                let strokes = try await environment.restClient.galleryPieceStrokes(pieceNumber: entry.pieceNumber)
                environment.studio.applyLoadedGalleryPiece(strokes)
            } catch {
                pauseIfRunning()
                environment.studio.clearViewing()
                environment.navigation.screen = .home
            }
        }
    }

    /// ux spec §1.1 "Gallery -> Home" row: pause-if-running, restore the
    /// saved live canvas (`CLEAR_VIEWING`, protocol-state spec §5.4) if a
    /// piece was being viewed, then always land on Home (not "wherever the
    /// gallery was opened from" — that's `closeGallery()`'s job, used by
    /// the header's X instead).
    private func goHome() {
        pauseIfRunning()
        environment.studio.clearViewing()
        environment.navigation.screen = .home
    }

    private func pauseIfRunning() {
        guard !environment.studio.state.paused else { return }
        environment.studio.setPausedLocally(true)
        environment.studio.send(.pause)
    }

    private func refresh() async {
        do {
            refreshedGallery = try await environment.restClient.gallery()
            refreshError = nil
        } catch {
            // Keep whatever we already had; only show the error state when
            // there's nothing else to show (see `emptyOrError`).
            if entries.isEmpty {
                refreshError = "Check your connection and try again."
            }
        }
    }
}

private struct GalleryCell: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    let entry: GalleryEntry
    let onSelect: () -> Void

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: FentonSpacing.small) {
                AuthenticatedThumbnailView(
                    token: entry.thumbnailToken,
                    fallbackSymbol: "photo",
                    contentMode: .fit
                )
                .aspectRatio(1, contentMode: .fit)
                .frame(maxWidth: .infinity)
                .background(CodeMonetDesignSystem.Extra.canvasBackground)
                .clipShape(RoundedRectangle(cornerRadius: FentonRadius.medium, style: .continuous))

                Text(GalleryFormatting.title(for: entry))
                    .font(FentonTypography.caption.weight(.semibold))
                    .foregroundStyle(palette.text)
                    .lineLimit(1)
                Text(GalleryFormatting.metaLine(for: entry))
                    .font(FentonTypography.tag)
                    .foregroundStyle(palette.tertiaryText)
                    .lineLimit(1)
            }
            .padding(FentonSpacing.small)
            .background(
                RoundedRectangle(cornerRadius: FentonRadius.large, style: .continuous)
                    .fill(palette.elevatedSurface)
            )
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("gallery-item-\(entry.pieceNumber)")
    }
}
