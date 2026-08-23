"""Authentication API routes."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from code_monet.auth.dependencies import CurrentUser
from code_monet.auth.email import send_magic_link_email
from code_monet.auth.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    get_user_id_from_token,
)
from code_monet.auth.password import hash_password, verify_password
from code_monet.auth.rate_limit import (
    MAGIC_LINK_BY_EMAIL,
    MAGIC_LINK_BY_IP,
    rate_limiter,
)
from code_monet.auth.schemas import (
    MagicLinkCodeVerifyRequest,
    MagicLinkRequest,
    MagicLinkVerifyRequest,
    MessageResponse,
    RefreshRequest,
    SigninRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from code_monet.config import settings
from code_monet.db import get_session, repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def require_legacy_auth() -> None:
    """Keep password and app-local magic-link endpoints development-only."""
    if not settings.dev_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_legacy_auth)],
)
async def signup(request: SignupRequest) -> TokenResponse:
    """Create a new user account with an invite code.

    Requires a valid, unused invite code.
    Returns JWT tokens on success.
    """
    async with get_session() as session:
        # Check if email already exists
        existing = await repository.get_user_by_email(session, request.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        # Validate invite code exists and is unused
        invite = await repository.get_invite_code(session, request.invite_code)
        if invite is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invite code",
            )
        if invite.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code already used",
            )

        # Create user
        password_hash = hash_password(request.password)
        user = await repository.create_user(session, request.email, password_hash)

        # Mark invite as used
        await repository.use_invite_code(session, request.invite_code, user.id)

        logger.info(f"User signed up: {user.email} (id={user.id})")

    # Generate tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/signin", response_model=TokenResponse, dependencies=[Depends(require_legacy_auth)])
async def signin(request: SigninRequest) -> TokenResponse:
    """Sign in with email and password.

    Returns JWT tokens on success.
    """
    async with get_session() as session:
        user = await repository.get_user_by_email(session, request.email)

    # Always verify password to prevent timing attacks
    # Use a dummy hash if user doesn't exist to equalize timing
    dummy_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.a8HkA6K1qRQDSu"
    password_hash = user.password_hash if user else dummy_hash
    password_valid = verify_password(request.password, password_hash)

    if user is None or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    logger.info(f"User signed in: {user.email} (id={user.id})")

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(require_legacy_auth)])
async def refresh(request: RefreshRequest) -> TokenResponse:
    """Refresh access token using a refresh token.

    Returns new JWT tokens on success.
    """
    try:
        user_id = get_user_id_from_token(request.refresh_token, expected_type="refresh")
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    async with get_session() as session:
        user = await repository.get_user_by_id(session, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> UserResponse:
    """Get current user info."""
    return UserResponse(id=user.id, email=user.email, is_active=user.is_active)


@router.post("/logout", response_model=MessageResponse)
async def logout(user: CurrentUser) -> MessageResponse:
    """Log out current user.

    Note: With JWT, logout is handled client-side by discarding tokens.
    This endpoint exists for API consistency and future token blacklisting.
    """
    logger.info(f"User logged out: {user.email} (id={user.id})")
    return MessageResponse(message="Logged out successfully")


@router.post(
    "/magic-link",
    response_model=MessageResponse,
    dependencies=[Depends(require_legacy_auth)],
)
async def request_magic_link(request: MagicLinkRequest, http_request: Request) -> MessageResponse:
    """Request a magic link for passwordless signin.

    Sends an email with a magic link if the user exists.
    Always returns success to prevent user enumeration.
    Rate limited to prevent abuse.
    """
    # Get client IP for rate limiting
    client_ip = http_request.client.host if http_request.client else "unknown"

    # Check rate limits (by IP and by email)
    if not rate_limiter.is_allowed(f"ip:{client_ip}", MAGIC_LINK_BY_IP):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
    if not rate_limiter.is_allowed(f"email:{request.email}", MAGIC_LINK_BY_EMAIL):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests for this email. Please try again later.",
        )

    async with get_session() as session:
        # Cleanup expired tokens periodically
        deleted = await repository.cleanup_expired_magic_links(session)
        if deleted > 0:
            logger.debug(f"Cleaned up {deleted} expired magic link tokens")

        user = await repository.get_user_by_email(session, request.email)

        # Only send email if user exists and is active
        if user and user.is_active:
            # Generate token and 6-digit code
            token = secrets.token_urlsafe(32)
            code = f"{secrets.randbelow(1000000):06d}"
            expires_at = datetime.now(UTC) + timedelta(minutes=settings.magic_link_expire_minutes)

            # Store token with code and platform
            await repository.create_magic_link_token(
                session,
                token=token,
                code=code,
                email=request.email,
                expires_at=expires_at,
                platform=request.platform,
            )

            # Build magic link URL
            magic_link_url = f"{settings.magic_link_base_url}/auth/verify?token={token}"

            # In dev mode, log the code for easy local testing
            if settings.dev_mode:
                logger.info(f"[DEV] Magic link code for {request.email}: {code}")

            # Send email (fire and forget - don't fail the request if email fails)
            email_sent = send_magic_link_email(request.email, magic_link_url, code)
            if email_sent:
                logger.info(f"Magic link sent to {request.email}")
            else:
                logger.warning(f"Failed to send magic link email to {request.email}")
        else:
            # Log but don't reveal to client
            logger.info(f"Magic link requested for non-existent/inactive user: {request.email}")

    # Always return success to prevent user enumeration
    return MessageResponse(message="If an account exists, a magic link has been sent to your email")


@router.get("/verify", response_class=HTMLResponse, dependencies=[Depends(require_legacy_auth)])
async def verify_magic_link_web(token: str = Query(...)) -> HTMLResponse:
    """Web handler for magic link verification.

    This endpoint is hit when the magic link is clicked in a browser
    (when iOS Universal Links don't intercept). It verifies the token
    and routes based on the platform that requested the magic link:
    - web: redirects to the web app with tokens
    - app: tries to open the iOS app with custom URL scheme
    """
    async with get_session() as session:
        magic_link = await repository.use_magic_link_token(session, token)

        if magic_link is None:
            return HTMLResponse(
                content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Link Expired - Code Monet</title>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; padding: 40px 20px; text-align: center; background: #f5f5f5; }
        .container { max-width: 400px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h1 { color: #333; font-size: 24px; margin-bottom: 16px; }
        p { color: #666; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Link Expired</h1>
        <p>This magic link has expired or has already been used.</p>
        <p>Please request a new sign-in link from the app.</p>
    </div>
</body>
</html>
""",
                status_code=401,
            )

        user = await repository.get_user_by_email(session, magic_link.email)

        if user is None or not user.is_active:
            return HTMLResponse(
                content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error - Code Monet</title>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; padding: 40px 20px; text-align: center; background: #f5f5f5; }
        .container { max-width: 400px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h1 { color: #333; font-size: 24px; margin-bottom: 16px; }
        p { color: #666; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Account Error</h1>
        <p>This account is not available.</p>
    </div>
</body>
</html>
""",
                status_code=401,
            )

        # Extract values before session closes
        platform = magic_link.platform
        logger.info(f"User signed in via magic link ({platform}): {user.email} (id={user.id})")

    # Generate tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    # Route based on platform that requested the magic link
    if platform == "web":
        # Redirect to web app with tokens in URL fragment (more secure than query params)
        web_url = f"{settings.magic_link_base_url}/auth/callback#access_token={access_token}&refresh_token={refresh_token}"

        return HTMLResponse(
            content=f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Signed In - Code Monet</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; padding: 40px 20px; text-align: center; background: #f5f5f5; }}
        .container {{ max-width: 400px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; font-size: 24px; margin-bottom: 16px; }}
        p {{ color: #666; line-height: 1.5; margin-bottom: 24px; }}
    </style>
    <script>
        // Redirect to web app
        window.location.href = "{web_url}";
    </script>
</head>
<body>
    <div class="container">
        <h1>Signing you in...</h1>
        <p>You'll be redirected automatically.</p>
    </div>
</body>
</html>
"""
        )

    # Default: app platform - try to open the iOS app with custom URL scheme
    app_url = f"codemonet://auth/callback?access_token={access_token}&refresh_token={refresh_token}"

    return HTMLResponse(
        content=f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Signed In - Code Monet</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; padding: 40px 20px; text-align: center; background: #f5f5f5; }}
        .container {{ max-width: 400px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; font-size: 24px; margin-bottom: 16px; }}
        p {{ color: #666; line-height: 1.5; margin-bottom: 24px; }}
        .button {{ display: inline-block; background: #000; color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 500; }}
        .button:hover {{ background: #333; }}
    </style>
    <script>
        // Try to open the app automatically
        window.location.href = "{app_url}";
    </script>
</head>
<body>
    <div class="container">
        <h1>You're signed in!</h1>
        <p>If the app doesn't open automatically, tap the button below.</p>
        <a href="{app_url}" class="button">Open Code Monet</a>
    </div>
</body>
</html>
"""
    )


@router.post(
    "/magic-link/verify",
    response_model=TokenResponse,
    dependencies=[Depends(require_legacy_auth)],
)
async def verify_magic_link(request: MagicLinkVerifyRequest) -> TokenResponse:
    """Verify a magic link token and return JWT tokens.

    The token must be valid, not expired, and not already used.
    """
    async with get_session() as session:
        # Attempt to use the token (marks it as used if valid)
        magic_link = await repository.use_magic_link_token(session, request.token)

        if magic_link is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired magic link",
            )

        # Get the user
        user = await repository.get_user_by_email(session, magic_link.email)

        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Extract values before session closes
        user_id = user.id
        user_email = user.email

        logger.info(f"User signed in via magic link: {user_email} (id={user_id})")

    # Generate tokens (outside session - only using extracted values)
    access_token = create_access_token(user_id, user_email)
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/magic-link/verify-code",
    response_model=TokenResponse,
    dependencies=[Depends(require_legacy_auth)],
)
async def verify_magic_link_code(request: MagicLinkCodeVerifyRequest) -> TokenResponse:
    """Verify a magic link using email and 6-digit code.

    Alternative to clicking the link - user can enter the code manually.
    The code must be valid, not expired, and not already used.
    """
    try:
        async with get_session() as session:
            # Attempt to use the code (marks it as used if valid)
            magic_link = await repository.use_magic_link_code(session, request.email, request.code)

            if magic_link is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired code",
                )

            # Get the user
            user = await repository.get_user_by_email(session, magic_link.email)

            if user is None or not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive",
                )

            # Extract values before session closes
            user_id = user.id
            user_email = user.email
            logger.info(f"User signed in via magic code: {user_email} (id={user_id})")

        # Generate tokens
        access_token = create_access_token(user_id, user_email)
        refresh_token = create_refresh_token(user_id)

        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error verifying magic code: {e}")
        raise
