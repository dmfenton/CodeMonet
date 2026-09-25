import FentonMobileCore
import Foundation

/// `MagicLinkAuthenticationClient` conformance for the Fenton Identity PKCE
/// flow (net-auth spec §2, §3.1). `identityAPI` talks to the fixed identity
/// host; `codeMonetAPI` talks to this app's own API (`GET /auth/me` — the
/// platform token has no email, so identity has to come from here).
public struct CodeMonetIdentityClient: MagicLinkAuthenticationClient {
    public static let clientID = "net.dmfenton.codemonet"
    public static let redirectURI = "https://monet.dmfenton.net/auth/callback"

    private let identityAPI: MobileAPIClient
    private let codeMonetAPI: MobileAPIClient

    public init(identityAPI: MobileAPIClient, codeMonetAPI: MobileAPIClient) {
        self.identityAPI = identityAPI
        self.codeMonetAPI = codeMonetAPI
    }

    public func requestMagicLink(email: String, codeChallenge: String) async throws -> MagicLinkRequestResult {
        do {
            return try await identityAPI.send(
                path: "/v1/authorization/requests",
                body: MagicLinkRequestBody(
                    email: email,
                    clientID: Self.clientID,
                    redirectURI: Self.redirectURI,
                    codeChallenge: codeChallenge,
                    codeChallengeMethod: "S256"
                ),
                response: MagicLinkRequestResult.self
            )
        } catch MobileAPIError.http(let statusCode) where statusCode == 400 {
            throw AuthenticationClientError.invalidAuthorizationCode
        }
    }

    public func exchangeAuthorizationCode(code: String, codeVerifier: String) async throws -> AuthSession {
        do {
            let response = try await identityAPI.send(
                path: "/v1/oauth/token",
                body: AuthorizationCodeGrantBody(code: code, codeVerifier: codeVerifier),
                response: TokenResponse.self
            )
            return response.session()
        } catch MobileAPIError.http(let statusCode) where statusCode == 400 {
            throw AuthenticationClientError.invalidAuthorizationCode
        }
    }

    public func refreshSession(refreshToken: String) async throws -> AuthSession {
        do {
            let response = try await identityAPI.send(
                path: "/v1/oauth/token",
                body: RefreshTokenGrantBody(refreshToken: refreshToken),
                response: TokenResponse.self
            )
            return response.session()
        } catch MobileAPIError.http(let statusCode) where statusCode == 400 {
            throw AuthenticationClientError.unauthorized
        }
    }

    /// `GET /auth/me` on `codeMonetAPI` — not the identity API (net-auth spec
    /// §3.1).
    public func fetchIdentity(bearerToken: String) async throws -> HouseholdIdentity {
        let data = try await codeMonetAPI.data(path: "/auth/me", bearerToken: bearerToken)
        let user = try codeMonetAPI.decode(data, as: IdentityUserResponse.self)
        return HouseholdIdentity(actorID: user.id, email: user.email, householdID: nil, householdName: nil)
    }
}

/// `POST /v1/authorization/requests` body (net-auth spec §2.1 step 3).
private struct MagicLinkRequestBody: Encodable {
    let email: String
    let clientID: String
    let redirectURI: String
    let codeChallenge: String
    let codeChallengeMethod: String
    enum CodingKeys: String, CodingKey {
        case email
        case clientID = "client_id"
        case redirectURI = "redirect_uri"
        case codeChallenge = "code_challenge"
        case codeChallengeMethod = "code_challenge_method"
    }
}

/// `POST /v1/oauth/token` (`grant_type=authorization_code`) body (net-auth
/// spec §2.1 step 6).
private struct AuthorizationCodeGrantBody: Encodable {
    let grantType = "authorization_code"
    let clientID = CodeMonetIdentityClient.clientID
    let redirectURI = CodeMonetIdentityClient.redirectURI
    let code: String
    let codeVerifier: String
    enum CodingKeys: String, CodingKey {
        case grantType = "grant_type"
        case clientID = "client_id"
        case redirectURI = "redirect_uri"
        case code
        case codeVerifier = "code_verifier"
    }
}

/// `POST /v1/oauth/token` (`grant_type=refresh_token`) body (net-auth spec
/// §2.2).
private struct RefreshTokenGrantBody: Encodable {
    let grantType = "refresh_token"
    let clientID = CodeMonetIdentityClient.clientID
    let refreshToken: String
    enum CodingKeys: String, CodingKey {
        case grantType = "grant_type"
        case clientID = "client_id"
        case refreshToken = "refresh_token"
    }
}

private struct IdentityUserResponse: Decodable {
    let id: String
    let email: String
    let isActive: Bool
    enum CodingKeys: String, CodingKey {
        case id, email
        case isActive = "is_active"
    }
}

/// `POST /v1/oauth/token` success shape (net-auth spec §2.1 step 6, §2.2).
private struct TokenResponse: Decodable {
    let accessToken: String
    let tokenType: String
    let expiresIn: Int
    let refreshToken: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
        case refreshToken = "refresh_token"
    }

    /// Sets `expiresAt`, unlike Garden's reference (net-auth spec §3.3) —
    /// that omission there defeats `AuthSession.isUsable`'s whole point.
    func session() -> AuthSession {
        AuthSession(
            bearerToken: accessToken,
            refreshToken: refreshToken,
            expiresAt: Date().addingTimeInterval(TimeInterval(expiresIn))
        )
    }
}
