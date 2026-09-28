import CoreImage.CIFilterBuiltins
import SwiftUI
import UIKit

/// A faint paper grain laid over an app surface, so large cream areas read
/// as paper rather than flat fill. The tile is generated once from Core
/// Image noise (no bundled asset) and tiled; it never covers a painting.
struct PaperGrain: View {
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if let tile = Self.tile {
            Image(uiImage: tile)
                .resizable(resizingMode: .tile)
                .opacity(colorScheme == .dark ? 0.035 : 0.05)
                .blendMode(colorScheme == .dark ? .screen : .multiply)
                .allowsHitTesting(false)
                .accessibilityHidden(true)
        }
    }

    private static let tile: UIImage? = {
        let side: CGFloat = 192
        let rect = CGRect(x: 0, y: 0, width: side, height: side)
        let noise = CIFilter.randomGenerator().outputImage?
            .cropped(to: rect)
            .applyingFilter("CIColorControls", parameters: [kCIInputSaturationKey: 0, kCIInputContrastKey: 0.9])
        guard let noise, let cgImage = CIContext().createCGImage(noise, from: rect) else { return nil }
        return UIImage(cgImage: cgImage, scale: 2, orientation: .up)
    }()
}
