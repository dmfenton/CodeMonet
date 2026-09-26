import MonetNetworking
import MonetRender
import SwiftUI

/// Shows a `.raster` gallery piece's final image — no reveal animation, no
/// vector strokes (program-painting spec §2.1's `galleryRasterImageUrl`
/// case). Deliberately separate from `PaintingRevealController`: a saved
/// piece being browsed has nothing to animate, so this is just a fetch +
/// decode + display, keyed by URL via `.task(id:)` so switching between
/// gallery pieces (or leaving/re-entering one) re-fetches correctly and
/// cancels any now-irrelevant in-flight load automatically.
struct GalleryRasterImageView: View {
    let urlString: String

    @State private var image: CGImage?
    @State private var loadedURLString: String?
    private let client = PaintingAssetClient()

    var body: some View {
        Group {
            if let image, loadedURLString == urlString {
                Image(decorative: image, scale: 1)
                    .resizable()
                    .accessibilityHidden(true)
            } else {
                Color.white
            }
        }
        .task(id: urlString) {
            do {
                let data = try await client.imageData(at: urlString)
                let decoded = try PaintingImageDecoder.decode(data)
                guard !Task.isCancelled else { return }
                image = decoded
                loadedURLString = urlString
            } catch {
                // Leave the previous image (or blank) on screen rather than
                // crash or show an error state over a transient fetch
                // failure — matches `PaintingRevealController`'s own
                // failure handling.
            }
        }
    }
}
