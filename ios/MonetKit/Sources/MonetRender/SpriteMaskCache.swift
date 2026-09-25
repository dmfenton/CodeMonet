import CoreGraphics
import Foundation
import MonetProtocol

/// Caches one `CGImage` stencil mask per `(brush, variant)` sprite (spec
/// §7.5-§7.6), built from `generateSpriteAlpha`'s alpha texture. Sprites are
/// cheap to regenerate (4 variants x ~12 brushes, a few thousand texels
/// each) but every stamp in a render references one, so caching keeps
/// `renderCommitted` from rebuilding the same texture thousands of times.
///
/// CoreGraphics's "image mask" convention (`CGImage(maskWidth:...)`, used
/// with `CGContext.clip(to:mask:)`) is a *stencil*: a pixel value of 0 means
/// "fully painted", 255 means "fully masked out" — the opposite polarity of
/// the sprite's own alpha-coverage values, so the cache inverts on build.
final class SpriteMaskCache: @unchecked Sendable {
    struct Mask {
        let image: CGImage
        /// Native sprite size in texels — the target rect callers scale
        /// this into can be any (non-uniform) size, since
        /// `CGContext.clip(to:mask:)` stretches the mask to fit.
        let width: Int
        let height: Int
    }

    static let shared = SpriteMaskCache()

    private let lock = NSLock()
    private var cache: [String: Mask] = [:]

    func mask(for brush: BrushName?, variant: Int) -> Mask? {
        let key = "\(brush?.rawValue ?? "default")#\(variant)"
        lock.lock()
        if let cached = cache[key] {
            lock.unlock()
            return cached
        }
        lock.unlock()

        guard let built = Self.build(brush: brush, variant: variant) else { return nil }
        lock.lock()
        cache[key] = built
        lock.unlock()
        return built
    }

    private static func build(brush: BrushName?, variant: Int) -> Mask? {
        let sprite = generateSpriteAlpha(brush: brush, variant: variant)
        guard sprite.width > 0, sprite.height > 0 else { return nil }

        var pixels = [UInt8](repeating: 0, count: sprite.width * sprite.height)
        for i in 0 ..< pixels.count {
            let coverage = clamp01(Double(sprite.data[i]))
            pixels[i] = UInt8(clamping: Int((255 - coverage * 255).rounded()))
        }

        guard let provider = CGDataProvider(data: Data(pixels) as CFData),
              let image = CGImage(
                  maskWidth: sprite.width, height: sprite.height,
                  bitsPerComponent: 8, bitsPerPixel: 8, bytesPerRow: sprite.width,
                  provider: provider, decode: nil, shouldInterpolate: true
              )
        else { return nil }

        return Mask(image: image, width: sprite.width, height: sprite.height)
    }
}
