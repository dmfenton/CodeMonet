import FentonMobileCore
import Foundation
import MonetProtocol

/// Supplies the current bearer token for an authenticated call. The app
/// target's `AuthService` implements this (platform access token in normal
/// operation, the DEBUG dev-token when no server session exists — net-auth
/// spec §3.4); `MonetNetworking` never talks to `AuthenticationController`
/// directly, keeping this package auth-implementation-agnostic.
public protocol TokenProviding: Sendable {
    func currentToken() async -> String?
}

/// The authenticated CodeMonet REST surface the app actually calls
/// (net-auth spec §6). Thin wrapper over `FentonMobileCore.MobileAPIClient`
/// — every method here corresponds to exactly one row of that table.
public struct CodeMonetRESTClient: Sendable {
    private let api: MobileAPIClient
    private let tokenProvider: any TokenProviding
    /// Net-auth spec §6/§9.2 point 2: a 401/403 (`MobileAPIError
    /// .unauthorized`, which covers both — see `APIClient.swift`) should
    /// trigger the same reactive-auth-failure handling as a live WS 4001.
    /// Fired with the bearer token this call was made with, so the caller
    /// can gate a sign-out against it still being the current token
    /// (`AuthService.signOut(ifBearerTokenMatches:)`) — a nil-token call
    /// (no session to begin with) never fires this.
    private let onUnauthorized: (@Sendable (String) async -> Void)?

    public init(
        baseURL: URL,
        tokenProvider: any TokenProviding,
        transport: any HTTPTransport = URLSession.shared,
        onUnauthorized: (@Sendable (String) async -> Void)? = nil
    ) {
        api = MobileAPIClient(baseURL: baseURL, transport: transport)
        self.tokenProvider = tokenProvider
        self.onUnauthorized = onUnauthorized
    }

    /// `GET /auth/me` — post-sign-in identity check (net-auth spec §0.2, §3.1).
    public func currentUser() async throws -> UserResponse {
        try await get("/auth/me", as: UserResponse.self)
    }

    /// `GET /auth/dev-token` — DEBUG-only bootstrap (net-auth spec §4). No
    /// auth header; 403s when the server isn't in dev mode.
    public func devToken() async throws -> DevTokenResponse {
        let data = try await api.data(path: "/auth/dev-token")
        return try api.decode(data, as: DevTokenResponse.self)
    }

    /// `GET /strokes/pending` — polled after `agent_strokes_ready`
    /// (protocol-state spec §2.4). Atomically pops the server's queue.
    public func pendingStrokes() async throws -> PendingStrokesResponse {
        try await get("/strokes/pending", as: PendingStrokesResponse.self)
    }

    /// `GET /gallery`.
    public func gallery() async throws -> [GalleryEntry] {
        try await get("/gallery", as: [GalleryEntry].self)
    }

    /// `GET /gallery/{piece_number}/strokes`.
    public func galleryPieceStrokes(pieceNumber: Int) async throws -> GalleryPieceStrokes {
        try await get("/gallery/\(pieceNumber)/strokes", as: GalleryPieceStrokes.self)
    }

    /// `GET /gallery/thumbnail/{piece_id}.png` — returns raw PNG bytes.
    /// `pieceID` is the gallery entry's `thumbnail_token`, formatted
    /// `piece_NNNNNN`.
    public func thumbnailData(pieceID: String) async throws -> Data {
        let token = await tokenProvider.currentToken()
        do {
            return try await api.data(path: "/gallery/thumbnail/\(pieceID).png", bearerToken: token)
        } catch MobileAPIError.unauthorized {
            if let token { await onUnauthorized?(token) }
            throw MobileAPIError.unauthorized
        }
    }

    private func get<Response: Decodable & Sendable>(_ path: String, as type: Response.Type) async throws -> Response {
        let token = await tokenProvider.currentToken()
        do {
            let data = try await api.data(path: path, bearerToken: token)
            return try api.decode(data, as: type)
        } catch MobileAPIError.unauthorized {
            if let token { await onUnauthorized?(token) }
            throw MobileAPIError.unauthorized
        }
    }
}

/// `GET /auth/me` response (net-auth spec §6).
public struct UserResponse: Codable, Equatable, Sendable {
    public var id: String
    public var email: String
    public var isActive: Bool

    enum CodingKeys: String, CodingKey {
        case id, email
        case isActive = "is_active"
    }

    public init(id: String, email: String, isActive: Bool) {
        self.id = id
        self.email = email
        self.isActive = isActive
    }
}

/// `GET /auth/dev-token` response (net-auth spec §4).
public struct DevTokenResponse: Codable, Equatable, Sendable {
    public var accessToken: String
    public var userID: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case userID = "user_id"
    }

    public init(accessToken: String, userID: String) {
        self.accessToken = accessToken
        self.userID = userID
    }
}
