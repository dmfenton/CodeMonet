import SwiftUI

/// One-shot splash overlay (ux spec §4). This is a functioning-but-simplified
/// placeholder — a static title + progress indicator that calls `onFinish`
/// after a fixed delay — standing in for the full gradient-orb/spring
/// animation sequence the spec describes in detail. The "app shell" work
/// package owns filling this in; the contract other code depends on is just
/// `SplashView(onFinish:)`.
struct SplashView: View {
    let onFinish: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Text("Code Monet")
                .font(.system(size: 32, weight: .light))
            Text("An autonomous AI artist")
                .font(.system(size: 16, weight: .regular))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(uiColor: .systemBackground))
        .task {
            try? await Task.sleep(nanoseconds: 800_000_000)
            onFinish()
        }
    }
}
