import CoreGraphics
import Foundation
@testable import MonetProtocol
@testable import MonetRender
import Testing

private struct AverageColor {
    var r: Double
    var g: Double
    var b: Double
}

@Suite("CoreGraphicsCanvasRenderer")
struct CanvasRendererTests {
    private func averageColor(_ image: CGImage) -> AverageColor {
        let width = image.width
        let height = image.height
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        guard let context = CGContext(
            data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
            space: colorSpace, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return AverageColor(r: 255, g: 255, b: 255) }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        guard let data = context.data else { return AverageColor(r: 255, g: 255, b: 255) }
        let buffer = data.bindMemory(to: UInt8.self, capacity: width * height * 4)
        var sumR = 0.0, sumG = 0.0, sumB = 0.0
        let count = width * height
        for i in 0 ..< count {
            sumR += Double(buffer[i * 4])
            sumG += Double(buffer[i * 4 + 1])
            sumB += Double(buffer[i * 4 + 2])
        }
        return AverageColor(r: sumR / Double(count), g: sumG / Double(count), b: sumB / Double(count))
    }

    @Test("an empty stroke list renders a plain white canvas at the exact requested size")
    func emptyStrokesIsWhite() throws {
        let renderer = CoreGraphicsCanvasRenderer()
        let image = try #require(renderer.renderCommitted(strokes: [], styleConfig: .paint, size: CGSize(width: 100, height: 80)))
        #expect(image.width == 100)
        #expect(image.height == 80)
        let avg = averageColor(image)
        #expect(avg.r > 254 && avg.g > 254 && avg.b > 254)
    }

    @Test("a paint-mode polyline stroke darkens the canvas below white")
    func paintStrokeDarkensCanvas() throws {
        let renderer = CoreGraphicsCanvasRenderer()
        let stroke = Path(
            type: .polyline,
            points: (0 ... 20).map { Point(x: Double($0) * 15, y: 200) },
            color: "#202040", strokeWidth: 14, opacity: 0.9, brush: .oilRound
        )
        let image = try #require(renderer.renderCommitted(strokes: [stroke], styleConfig: .paint, size: CGSize(width: 400, height: 400)))
        let avg = averageColor(image)
        #expect(avg.r < 254 || avg.g < 254 || avg.b < 254)
    }

    @Test("a plotter-mode stroke ignores per-path color/width overrides")
    func plotterModeIgnoresOverrides() throws {
        let renderer = CoreGraphicsCanvasRenderer()
        // Bright red, 20px request — plotter mode should render it as the
        // style config's monochrome agent-stroke default (#1a1a2e, 2.5px)
        // instead (performer-render spec §2.5/§14).
        let stroke = Path(
            type: .line, points: [Point(x: 50, y: 200), Point(x: 350, y: 200)],
            color: "#FF0000", strokeWidth: 20, opacity: 1.0
        )
        let image = try #require(renderer.renderCommitted(strokes: [stroke], styleConfig: .plotter, size: CGSize(width: 400, height: 400)))
        let avg = averageColor(image)
        // A thin (~2.5px) dark line only covers a tiny fraction of a
        // 400x400 canvas, so the whole-image average barely moves — just
        // confirm it moved off pure white at all. A 20px bright-red line
        // (the requested override) would also move the average, so this
        // alone doesn't fully prove the override was ignored; the pixel
        // sampling below checks color directly.
        #expect(avg.r < 254.9)

        // Sample along the line's path and confirm no pixel is anywhere
        // near the requested bright red (#FF0000) — plotter mode should
        // have used the style config's monochrome default instead.
        let width = image.width
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let sampleContext = try #require(CGContext(
            data: nil, width: width, height: image.height, bitsPerComponent: 8, bytesPerRow: width * 4,
            space: colorSpace, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ))
        sampleContext.draw(image, in: CGRect(x: 0, y: 0, width: width, height: image.height))
        let buffer = try #require(sampleContext.data).bindMemory(to: UInt8.self, capacity: width * image.height * 4)
        var sawBrightRed = false
        for x in stride(from: 50, through: 350, by: 5) {
            let y = 200
            let offset = (y * width + x) * 4
            let r = buffer[offset], g = buffer[offset + 1], b = buffer[offset + 2]
            if r > 200, g < 60, b < 60 { sawBrightRed = true }
        }
        #expect(!sawBrightRed)
    }

    @Test("a single-point path draws a dot, not nothing")
    func singlePointDrawsDot() throws {
        let renderer = CoreGraphicsCanvasRenderer()
        let stroke = Path(type: .polyline, points: [Point(x: 200, y: 200)], color: "#000000", strokeWidth: 10, opacity: 1)
        let image = try #require(renderer.renderCommitted(strokes: [stroke], styleConfig: .paint, size: CGSize(width: 400, height: 400)))
        let avg = averageColor(image)
        #expect(avg.r < 254.9)
    }

    @Test("an SVG-type path with a fill renders non-white pixels")
    func svgFillRenders() throws {
        let renderer = CoreGraphicsCanvasRenderer()
        let stroke = Path(type: .svg, d: "M50 50 L350 50 L350 350 L50 350 Z", fill: "#336699", fillOpacity: 1.0)
        let image = try #require(renderer.renderCommitted(strokes: [stroke], styleConfig: .paint, size: CGSize(width: 400, height: 400)))
        let avg = averageColor(image)
        // A large filled square should pull the average well below white.
        #expect(avg.b < 240)
    }

    @Test("zero-size canvas requests still return a 1x1 image, not a crash")
    func degenerateSizeIsHandled() throws {
        let renderer = CoreGraphicsCanvasRenderer()
        let image = try #require(renderer.renderCommitted(strokes: [], styleConfig: .paint, size: CGSize(width: 0, height: 0)))
        #expect(image.width == 1)
        #expect(image.height == 1)
    }
}
