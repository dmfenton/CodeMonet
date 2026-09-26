import FentonDesignSystem
import SwiftUI

/// One-shot splash overlay (ux spec §4). A fixed, non-interactive,
/// non-skippable ~2.4s animation sequence — not a route, mounted once by
/// `RootView` on top of the main app for the first pass through a fresh
/// launch. Timing budget matches the spec's five numbered steps exactly
/// (600 + 500 + 800 + 500 = 2400ms); the title's spring (step 2, no
/// duration given in the spec) starts at the same instant as step 3's
/// subtitle/icon fade rather than adding its own sequential delay, which is
/// the only way the spec's own numbers add up to "~2.4s total".
struct SplashView: View {
    let onFinish: () -> Void

    @Environment(\.fentonTheme) private var fentonTheme
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var backgroundOpacity: Double = 0
    @State private var titleOffset: CGFloat = 40
    @State private var titleScale: CGFloat = 0.9
    @State private var titleOpacity: Double = 0
    @State private var subtitleOpacity: Double = 0
    @State private var overlayOpacity: Double = 1
    @State private var orbsDrifting = false

    private var palette: FentonTheme.Palette { fentonTheme.palette(for: colorScheme) }

    var body: some View {
        ZStack {
            background
            foreground
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(palette.surface)
        .opacity(overlayOpacity)
        .ignoresSafeArea()
        // Decorative, non-interactive, no skip/tap in the source (ux spec
        // §4) — VoiceOver should skip straight past it to the app beneath.
        .accessibilityHidden(true)
        .task { await runSequence() }
    }

    // MARK: - Background (orbs, splatters, brush strokes)

    private var background: some View {
        GeometryReader { proxy in
            let size = proxy.size
            ZStack {
                orb(color: palette.accent, diameter: size.width * 0.55, relativeCenter: (0.22, 0.28), drift: -20, period: 3)
                orb(color: palette.emphasis, diameter: size.width * 0.5, relativeCenter: (0.82, 0.68), drift: 15, period: 2.5)
                ForEach(Self.splatters(palette: palette)) { spot in
                    Circle()
                        .fill(spot.color)
                        .frame(width: spot.diameter, height: spot.diameter)
                        .position(x: size.width * spot.x, y: size.height * spot.y)
                        .opacity(0.15)
                }
                ForEach(Self.brushStrokes(palette: palette)) { stroke in
                    BrushStrokeShape()
                        .stroke(stroke.color, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                        .frame(width: 90, height: 34)
                        .rotationEffect(.degrees(stroke.rotationDegrees))
                        .position(x: size.width * stroke.x, y: size.height * stroke.y)
                        .opacity(0.4)
                }
            }
        }
        .opacity(backgroundOpacity)
    }

    private func orb(
        color: Color,
        diameter: CGFloat,
        relativeCenter: (x: CGFloat, y: CGFloat),
        drift: CGFloat,
        period: Double
    ) -> some View {
        GeometryReader { proxy in
            Circle()
                .fill(
                    RadialGradient(
                        colors: [color.opacity(0.55), color.opacity(0)],
                        center: .center,
                        startRadius: 0,
                        endRadius: diameter / 2
                    )
                )
                .frame(width: diameter, height: diameter)
                .position(
                    x: proxy.size.width * relativeCenter.x,
                    y: proxy.size.height * relativeCenter.y + (orbsDrifting ? drift : 0)
                )
                .animation(
                    reduceMotion ? nil : .easeInOut(duration: period).repeatForever(autoreverses: true),
                    value: orbsDrifting
                )
        }
    }

    // MARK: - Foreground (title, subtitle, glow badge, footer)

    private var foreground: some View {
        VStack(spacing: 0) {
            Spacer()
            VStack(spacing: 12) {
                titleRow
                underlineBars
                Text("An autonomous AI artist")
                    .font(.system(size: 22, design: .serif).italic())
                    .foregroundStyle(palette.secondaryText)
                    .opacity(subtitleOpacity)
                glowBadge
                    .padding(.top, 8)
                    .opacity(subtitleOpacity)
            }
            Spacer()
            Text("Powered by Claude")
                .font(.system(size: 11, weight: .semibold))
                .textCase(.uppercase)
                .tracking(2)
                .foregroundStyle(palette.tertiaryText)
                .padding(.bottom, 48)
                .opacity(subtitleOpacity)
        }
    }

    private var titleRow: some View {
        BrandLockup(markSize: 72, wordSize: 48)
            .offset(y: titleOffset)
            .scaleEffect(titleScale)
            .opacity(titleOpacity)
    }

    private var underlineBars: some View {
        HStack(spacing: 4) {
            Capsule().fill(palette.accent).frame(width: 60, height: 3)
            Capsule().fill(palette.emphasis).frame(width: 40, height: 3)
        }
        .offset(y: titleOffset)
        .opacity(titleOpacity)
    }

    private var glowBadge: some View {
        Image(systemName: "paintbrush.pointed.fill")
            .font(.system(size: 18))
            .foregroundStyle(palette.surface)
            .frame(width: 44, height: 44)
            .background(Circle().fill(palette.accent))
            .accessibilityHidden(true)
    }

    // MARK: - Animation sequence

    private func runSequence() async {
        guard !reduceMotion else {
            // Reduce Motion: show the final state briefly rather than
            // running the decorative drift/spring/fade sequence.
            backgroundOpacity = 1
            titleOffset = 0
            titleScale = 1
            titleOpacity = 1
            subtitleOpacity = 1
            try? await Task.sleep(nanoseconds: 400_000_000)
            onFinish()
            return
        }

        orbsDrifting = true

        withAnimation(.easeIn(duration: 0.6)) { backgroundOpacity = 1 }
        try? await Task.sleep(nanoseconds: 600_000_000)

        withAnimation(.interpolatingSpring(stiffness: 170, damping: 15)) {
            titleOffset = 0
            titleScale = 1
            titleOpacity = 1
        }
        withAnimation(.easeIn(duration: 0.5)) { subtitleOpacity = 1 }
        try? await Task.sleep(nanoseconds: 500_000_000)

        try? await Task.sleep(nanoseconds: 800_000_000)

        withAnimation(.easeOut(duration: 0.5)) { overlayOpacity = 0 }
        try? await Task.sleep(nanoseconds: 500_000_000)

        onFinish()
    }

    // MARK: - Decorative spec data

    private struct Splatter: Identifiable {
        let id: Int
        let x: CGFloat
        let y: CGFloat
        let diameter: CGFloat
        let color: Color
    }

    private struct BrushStroke: Identifiable {
        let id: Int
        let x: CGFloat
        let y: CGFloat
        let rotationDegrees: Double
        let color: Color
    }

    private static func splatters(palette: FentonTheme.Palette) -> [Splatter] {
        [
            Splatter(id: 0, x: 0.12, y: 0.16, diameter: 18, color: palette.accent),
            Splatter(id: 1, x: 0.86, y: 0.22, diameter: 14, color: palette.warning),
            Splatter(id: 2, x: 0.78, y: 0.82, diameter: 20, color: palette.success),
            Splatter(id: 3, x: 0.16, y: 0.85, diameter: 16, color: palette.emphasis)
        ]
    }

    private static func brushStrokes(palette: FentonTheme.Palette) -> [BrushStroke] {
        [
            BrushStroke(id: 0, x: 0.2, y: 0.36, rotationDegrees: -20, color: palette.accent),
            BrushStroke(id: 1, x: 0.8, y: 0.3, rotationDegrees: 15, color: palette.success),
            BrushStroke(id: 2, x: 0.25, y: 0.76, rotationDegrees: 35, color: palette.emphasis),
            BrushStroke(id: 3, x: 0.82, y: 0.78, rotationDegrees: -30, color: palette.emphasis)
        ]
    }
}

/// A quadratic-bezier "S" squiggle (ux spec §4's `BrushStroke` decoration).
private struct BrushStrokeShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let midY = rect.midY
        path.move(to: CGPoint(x: rect.minX, y: midY))
        path.addQuadCurve(
            to: CGPoint(x: rect.midX, y: rect.minY),
            control: CGPoint(x: rect.minX + rect.width * 0.25, y: rect.minY)
        )
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX, y: midY),
            control: CGPoint(x: rect.maxX - rect.width * 0.25, y: rect.maxY)
        )
        return path
    }
}
