import CoreGraphics
import Foundation
import ImageIO
#if canImport(UniformTypeIdentifiers)
    import UniformTypeIdentifiers
#endif

public enum PNGWriter {
    public enum WriteError: Error { case destinationCreationFailed, finalizeFailed }

    /// Writes `image` to `url` as PNG. Used by `monet-render` and by any
    /// test/tooling that wants to inspect a rendered frame on disk.
    public static func write(_ image: CGImage, to url: URL) throws {
        let type: CFString
        if #available(macOS 11.0, iOS 14.0, *) {
            type = UTType.png.identifier as CFString
        } else {
            type = "public.png" as CFString
        }
        guard let destination = CGImageDestinationCreateWithURL(url as CFURL, type, 1, nil) else {
            throw WriteError.destinationCreationFailed
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else {
            throw WriteError.finalizeFailed
        }
    }
}
