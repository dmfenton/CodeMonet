import Foundation

/// The three mutually-exclusive top-level screens (ux spec §1). Gallery is
/// not a fourth peer screen conceptually — it always remembers which of
/// these it was opened from — but is still modeled as a case here since the
/// app does render it full-screen rather than as a sheet-over-Studio; the
/// "remembers where it came from" behavior lives in `NavigationState`.
public enum AppScreen: Equatable, Sendable {
    case home
    case studio
    case gallery
}

/// Screen-transition side effects (ux spec §1.1) live in `StudioStore`/
/// `AuthService` calls made by the view layer around a `NavigationState`
/// mutation — this type only tracks *where the user is*, not the pause/
/// resume/clear-viewing effects a transition implies. Kept as a small
/// `@Observable` so the app shell and feature views share one instance
/// without threading bindings through every view.
@MainActor
@Observable
public final class NavigationState {
    public var screen: AppScreen = .home
    /// Which screen opened the gallery, so its header can offer the right
    /// "back"/"home" affordances (ux spec §8).
    public var galleryOpenedFrom: AppScreen = .home

    public init() {}

    /// A piece the gallery should open straight into (Home's recent row).
    /// Consumed (cleared) by the gallery once shown.
    public var galleryFocusPiece: Int?

    public func openGallery(from screen: AppScreen, focusing pieceNumber: Int? = nil) {
        galleryOpenedFrom = screen
        galleryFocusPiece = pieceNumber
        self.screen = .gallery
    }

    public func closeGallery() {
        screen = galleryOpenedFrom
    }
}
