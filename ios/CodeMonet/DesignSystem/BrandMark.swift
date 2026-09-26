import SwiftUI

/// The Code Monet lily pad, drawn natively from `brand/mark.svg`'s geometry
/// (100x100 box): a pad of radius 34 centered at (50, 50) with a notch
/// between -98° and -82° (the cursor slot), seven veins from the center, and
/// a terracotta pen-point dot. The mark's colors are fixed brand colors —
/// they read on both light and dark surfaces, like the app icon.
struct BrandMark: View {
    var size: CGFloat = 28

    private static let padColor = Color(hex: "#2a6243")
    private static let veinColor = Color(hex: "#94b89e")
    private static let dotColor = Color(hex: "#b85a2e")

    /// Vein endpoints from `mark.svg`, in the 100x100 box.
    private static let veinEnds: [CGPoint] = [
        CGPoint(x: 73.4, y: 36.5), CGPoint(x: 76.6, y: 54.7), CGPoint(x: 67.4, y: 70.7),
        CGPoint(x: 50, y: 77), CGPoint(x: 32.6, y: 70.7), CGPoint(x: 23.4, y: 54.7),
        CGPoint(x: 26.6, y: 36.5),
    ]

    var body: some View {
        Canvas { context, canvasSize in
            let scale = min(canvasSize.width, canvasSize.height) / 100
            context.scaleBy(x: scale, y: scale)
            let center = CGPoint(x: 50, y: 50)

            var pad = Path()
            pad.move(to: center)
            // Clockwise in screen space from -82° round to -98°, leaving the notch open.
            pad.addArc(center: center, radius: 34, startAngle: .degrees(-82), endAngle: .degrees(-98), clockwise: false)
            pad.closeSubpath()
            context.fill(pad, with: .color(Self.padColor))

            var veins = Path()
            for end in Self.veinEnds {
                veins.move(to: center)
                veins.addLine(to: end)
            }
            context.stroke(veins, with: .color(Self.veinColor), style: StrokeStyle(lineWidth: 1.8, lineCap: .round))

            let dot = CGRect(x: 50 - 5.8, y: 50 - 5.8, width: 11.6, height: 11.6)
            context.fill(Path(ellipseIn: dot), with: .color(Self.dotColor))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// Mark + wordmark lockup: "code" small monospaced in the accent over
/// "Monet" in serif italic.
struct BrandLockup: View {
    var markSize: CGFloat = 30
    var wordSize: CGFloat = 20
    var showsCode = true
    /// `false` for a wordmark-only lockup (e.g. under a larger standalone mark).
    var showsMark = true

    var body: some View {
        PaletteReader { palette in
            HStack(spacing: markSize * 0.3) {
                if showsMark {
                    BrandMark(size: markSize)
                }
                VStack(alignment: .leading, spacing: 0) {
                    if showsCode {
                        Text("code")
                            .font(.system(size: wordSize * 0.55, weight: .medium, design: .monospaced))
                            .foregroundStyle(palette.accent)
                    }
                    Text("Monet")
                        .font(.system(size: wordSize, design: .serif).italic())
                        .foregroundStyle(palette.text)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Code Monet")
        }
    }
}

#Preview {
    VStack(spacing: 24) {
        BrandMark(size: 120)
        BrandLockup()
        BrandLockup(markSize: 26, wordSize: 19, showsCode: false)
    }
    .padding()
    .fentonTheme(CodeMonetDesignSystem.theme)
}
