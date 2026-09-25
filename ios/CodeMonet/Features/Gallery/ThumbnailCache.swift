import Foundation
import MonetNetworking
import Observation
import UIKit

/// Adapts `AuthService`'s bearer token to `MonetNetworking.TokenProviding`
/// for feature-owned `CodeMonetRESTClient` instances. Mirrors the private
/// `AuthServiceTokenProvider` in `App/AppEnvironment.swift` — duplicated
/// rather than shared because that type is `private` to its file (owned by
/// the app-shell work package); this is a small enough adapter that the
/// duplication is cheaper than a cross-package API change.
struct FeatureAuthTokenProvider: TokenProviding {
    let auth: AuthService
    func currentToken() async -> String? {
        await auth.bearerToken
    }
}

extension AppEnvironment {
    /// A `CodeMonetRESTClient` for feature code that needs REST calls beyond
    /// what `StudioStore` exposes (thumbnails, a manual gallery refresh).
    /// Built fresh per call — it's a thin, stateless wrapper over
    /// `URLSession.shared`, not a connection to hold onto.
    var restClient: CodeMonetRESTClient {
        CodeMonetRESTClient(baseURL: config.apiBaseURL, tokenProvider: FeatureAuthTokenProvider(auth: auth))
    }
}

/// An in-memory, app-session-lifetime cache of decoded gallery thumbnails,
/// keyed by `GalleryEntry.thumbnailToken` (ux spec §8, §9.2). Shared across
/// Home's Continue card and the Gallery grid via `static let shared` —
/// `AppEnvironment` (app-shell-owned) doesn't currently have a slot for a
/// feature-local cache, and Home/Gallery are mutually-exclusive sibling
/// screens with no shared ancestor view within this package's owned paths
/// to hold one. A future `AppEnvironment` addition could own this instead;
/// noted as a follow-up rather than reaching into app-shell's file for it.
@MainActor
@Observable
final class ThumbnailCache {
    static let shared = ThumbnailCache()

    private var images: [String: UIImage] = [:]
    private var inFlight: Set<String> = []
    private var failed: Set<String> = []

    private init() {}

    func image(for token: String) -> UIImage? {
        images[token]
    }

    func didFail(_ token: String) -> Bool {
        failed.contains(token)
    }

    /// Fetches and decodes the thumbnail if it isn't already cached or
    /// in-flight. Safe to call redundantly (e.g. from every grid cell's
    /// `.task`) — de-duplicates by token.
    func load(token: String, using rest: CodeMonetRESTClient) async {
        guard images[token] == nil, !inFlight.contains(token) else { return }
        inFlight.insert(token)
        defer { inFlight.remove(token) }
        do {
            let data = try await rest.thumbnailData(pieceID: token)
            if let image = UIImage(data: data) {
                images[token] = image
                failed.remove(token)
            } else {
                failed.insert(token)
            }
        } catch {
            failed.insert(token)
        }
    }
}
