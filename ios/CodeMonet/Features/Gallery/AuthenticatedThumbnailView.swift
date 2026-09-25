import FentonDesignSystem
import SwiftUI

/// Loads and shows a gallery piece's authenticated thumbnail
/// (`/gallery/thumbnail/{token}.png`, ux spec §9.2), backed by
/// `ThumbnailCache`. Shows a spinner while loading and a fallback SF Symbol
/// on error or absence — used by both the Home Continue card and the
/// Gallery grid.
struct AuthenticatedThumbnailView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.fentonTheme) private var theme

    let token: String?
    var fallbackSymbol: String = "photo"
    var fallbackText: String?
    var contentMode: ContentMode = .fit

    var body: some View {
        let palette = theme.palette(for: colorScheme)
        ZStack {
            if let token, let image = ThumbnailCache.shared.image(for: token) {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
                    .accessibilityLabel("Artwork thumbnail")
            } else if let token, !ThumbnailCache.shared.didFail(token) {
                ProgressView()
                    .tint(palette.tertiaryText)
            } else {
                VStack(spacing: FentonSpacing.small) {
                    Image(systemName: fallbackSymbol)
                        .font(.system(size: 28, weight: .light))
                        .foregroundStyle(palette.tertiaryText)
                        .accessibilityHidden(true)
                    if let fallbackText {
                        Text(fallbackText)
                            .font(FentonTypography.caption)
                            .foregroundStyle(palette.tertiaryText)
                    }
                }
            }
        }
        .task(id: token) {
            guard let token else { return }
            await ThumbnailCache.shared.load(token: token, using: environment.restClient)
        }
    }
}
