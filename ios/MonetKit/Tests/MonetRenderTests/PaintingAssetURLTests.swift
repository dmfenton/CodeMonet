import Foundation
@testable import MonetProtocol
@testable import MonetRender
import Testing

@Suite("PaintingAssetURL")
struct PaintingAssetURLTests {
    @Test("joins API-relative paths onto the API base")
    func joinsApiRelativePaths() {
        #expect(
            PaintingAssetURL.apiAssetUrl("http://localhost:8000", "/painting-assets/u/t/final.png")
                == "http://localhost:8000/painting-assets/u/t/final.png"
        )
        #expect(
            PaintingAssetURL.apiAssetUrl("https://monet.dmfenton.net/api/", "/painting-assets/x")
                == "https://monet.dmfenton.net/api/painting-assets/x"
        )
        #expect(
            PaintingAssetURL.apiAssetUrl("http://a", "https://cdn/x.png") == "https://cdn/x.png"
        )
        #expect(
            PaintingAssetURL.paintingAssetUrl(apiBase: "http://a/", assetBase: "/painting-assets/u/t/", file: PaintingAssetURL.performanceFile)
                == "http://a/painting-assets/u/t/performance.bin"
        )
    }

    @Test("only resolves raster pieces with an image_url")
    func onlyResolvesRasterWithImageURL() {
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .strokes, imageURL: "/x.png") == nil)
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .raster, imageURL: nil) == nil)
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .other(""), imageURL: "/x.png") == nil)
        #expect(PaintingAssetURL.galleryRasterImageUrl(apiBase: "http://a", format: .raster, imageURL: "/x.png") == "http://a/x.png")
    }
}
