import MonetProtocol

/// Resolves program-painting asset URLs: a version's (or live run's)
/// `asset_base` + file name, joined onto the API base URL. Asset URLs are
/// capability URLs (no auth), like share links.
public enum PaintingAssetURL {
    /// Joins an API-relative `path` onto `apiBase` (program-painting spec
    /// §2.1, `apiAssetUrl`). A trailing slash on `apiBase` is stripped
    /// before joining; a `path` that's already absolute (carries its own
    /// scheme, e.g. a CDN URL) passes through unchanged.
    public static func apiAssetUrl(_ apiBase: String, _ path: String) -> String {
        if path.contains("://") { return path }
        let base = apiBase.hasSuffix("/") ? String(apiBase.dropLast()) : apiBase
        return base + path
    }

    /// A painting version's `asset_base` + filename, resolved against the
    /// API base (spec §2.1, `paintingAssetUrl`). `asset_base` always ends
    /// in `/`.
    public static func paintingAssetUrl(apiBase: String, ref: PaintingVersionRef, file: String) -> String {
        apiAssetUrl(apiBase, ref.assetBase + file)
    }

    /// `asset_base` + filename for any asset base (a version's, or a live
    /// run's before it is recorded).
    public static func paintingAssetUrl(apiBase: String, assetBase: String, file: String) -> String {
        apiAssetUrl(apiBase, assetBase + file)
    }

    /// A version's final picture.
    public static let finalFile = "final.png"
    /// A version's performance stream (docs/program-painting.md "Live
    /// performance"); `PERFORMANCE_FILE` in `shared/src/renderer/performance.ts`.
    public static let performanceFile = "performance.bin"

    /// Only resolves for a raster piece with a non-nil `image_url` (spec §8
    /// test 11, `galleryRasterImageUrl`) — `nil` for `.strokes` regardless
    /// of `imageURL`, and for `.raster` with a `nil` `imageURL`.
    public static func galleryRasterImageUrl(apiBase: String, format: GalleryPieceFormat, imageURL: String?) -> String? {
        guard format == .raster, let imageURL else { return nil }
        return apiAssetUrl(apiBase, imageURL)
    }
}
