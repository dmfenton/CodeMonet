import CoreGraphics
import Foundation
import ImageIO

/// Decodes raw image bytes (`final.png`, a performance atlas WebP) via
/// ImageIO, so nothing in the app target has to reach for ImageIO directly.
public enum PaintingImageDecoder {
    public enum DecodeError: Error, Equatable, Sendable {
        case invalidData
        /// The image is larger than `RGBAPixels.maxPixelCount` (untrusted
        /// program output must not make the app allocate without bound).
        case tooLarge(width: Int, height: Int)
    }

    public static func decode(_ data: Data) throws -> CGImage {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else {
            throw DecodeError.invalidData
        }
        return image
    }

    /// Decodes to 8-bit RGBA (sRGB, row 0 = top), for pixel-level work.
    public static func decodeRGBA(_ data: Data) throws -> RGBAPixels {
        try RGBAPixels(image: decode(data))
    }
}

/// An 8-bit RGBA bitmap in memory: row 0 is the top row, 4 bytes per pixel,
/// no row padding. Opaque content has alpha 255.
public struct RGBAPixels: Sendable, Equatable {
    public let width: Int
    public let height: Int
    public var bytes: [UInt8]

    /// Upper bound on any bitmap decoded from program output (4096 x 4096):
    /// a painting's image is at most 2x its canvas, well under this.
    public static let maxPixelCount = 4096 * 4096

    /// A `width` x `height` bitmap filled with opaque white.
    public init(width: Int, height: Int) {
        self.width = width
        self.height = height
        bytes = [UInt8](repeating: 255, count: width * height * 4)
    }

    /// Draws `image` into a fresh bitmap of its own size.
    public init(image: CGImage) throws {
        guard image.width > 0, image.height > 0 else { throw PaintingImageDecoder.DecodeError.invalidData }
        guard image.width * image.height <= Self.maxPixelCount else {
            throw PaintingImageDecoder.DecodeError.tooLarge(width: image.width, height: image.height)
        }
        self.init(width: image.width, height: image.height)
        guard draw(image) else { throw PaintingImageDecoder.DecodeError.invalidData }
    }

    /// Draws `image` scaled to fill the whole bitmap (over what is there).
    @discardableResult
    public mutating func draw(_ image: CGImage) -> Bool {
        let width = width
        let height = height
        return bytes.withUnsafeMutableBytes { raw -> Bool in
            guard let context = CGContext(
                data: raw.baseAddress,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: width * 4,
                space: CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.interpolationQuality = .high
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
    }

    /// A `CGImage` holding a copy of the current pixels.
    public func makeImage() -> CGImage? {
        guard let provider = CGDataProvider(data: Data(bytes) as CFData) else { return nil }
        return CGImage(
            width: width,
            height: height,
            bitsPerComponent: 8,
            bitsPerPixel: 32,
            bytesPerRow: width * 4,
            space: CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
            provider: provider,
            decode: nil,
            shouldInterpolate: true,
            intent: .defaultIntent
        )
    }
}
