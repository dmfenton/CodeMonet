import FentonMobileCore
import Foundation
import MonetProtocol

/// Fetches program-painting version assets — `reveal.json` and the
/// keyframe/`final.png` images it references — directly from their
/// resolved, capability-token URLs (`MonetRender.PaintingAssetURL`,
/// program-painting spec §2.1). Deliberately **not** routed through
/// `CodeMonetRESTClient`/`MobileAPIClient`: those always attach a bearer
/// token and resolve a path relative to `baseURL`, but painting-asset URLs
/// carry their own unguessable per-version token and are meant to load
/// "like share links" (server's `routes/paintings.py` doc comment) — no
/// auth header, and already fully resolved (absolute) strings by the time
/// they reach here.
public struct PaintingAssetClient: Sendable {
    private let transport: any HTTPTransport

    public init(transport: any HTTPTransport = URLSession.shared) {
        self.transport = transport
    }

    public enum FetchError: Error, Equatable, Sendable {
        case invalidURL(String)
        case http(statusCode: Int)
        case decoding(String)
    }

    /// Fetches and decodes a `reveal.json` manifest (program-painting spec
    /// §3.3).
    public func manifest(at urlString: String) async throws -> RevealManifest {
        let raw = try await data(at: urlString)
        do {
            return try JSONDecoder().decode(RevealManifest.self, from: raw)
        } catch {
            throw FetchError.decoding(String(describing: error))
        }
    }

    /// Fetches raw image bytes for a keyframe (`kf_NN.jpg`) or `final.png`.
    /// Decoding to a drawable image is the caller's job (`MonetRender`
    /// owns `CGImage`, not this package).
    public func imageData(at urlString: String) async throws -> Data {
        try await data(at: urlString)
    }

    /// Fetches a version's `painting.py` (the program that rendered it) as
    /// UTF-8 text.
    public func text(at urlString: String) async throws -> String {
        let raw = try await data(at: urlString)
        guard let text = String(data: raw, encoding: .utf8) else {
            throw FetchError.decoding("not UTF-8 text")
        }
        return text
    }

    private func data(at urlString: String) async throws -> Data {
        guard let url = URL(string: urlString) else {
            throw FetchError.invalidURL(urlString)
        }
        let (data, response) = try await transport.data(for: URLRequest(url: url))
        if let http = response as? HTTPURLResponse, !(200 ..< 300).contains(http.statusCode) {
            throw FetchError.http(statusCode: http.statusCode)
        }
        return data
    }
}
