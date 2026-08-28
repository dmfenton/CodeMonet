"""Application configuration."""

import logging
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


@lru_cache
def _get_ssm_params() -> dict[str, str]:
    """Fetch all params from SSM for current environment.

    Returns empty dict if SSM is unavailable (e.g., missing credentials).
    """
    env = os.getenv("CODE_MONET_ENV", "dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    path = f"/code-monet/{env}/"

    try:
        import boto3

        ssm = boto3.client("ssm", region_name=region)
        resp = ssm.get_parameters_by_path(Path=path, WithDecryption=True)
        params = {
            p["Name"].split("/")[-1].replace("-", "_"): p["Value"] for p in resp["Parameters"]
        }
        logger.info(f"Loaded {len(params)} parameters from SSM ({path})")
        return params
    except Exception as e:
        logger.warning(f"Failed to load SSM parameters from {path}: {e}")
        return {}


def _ssm(key: str, default: str = "") -> str:
    """Get config value from SSM, with optional default.

    Treats "NONE" as empty string (SSM doesn't allow empty values).
    """
    value = _get_ssm_params().get(key, default)
    return "" if value == "NONE" else value


class Settings(BaseSettings):
    """Application settings loaded from SSM Parameter Store and environment variables.

    Priority: SSM > environment variables > defaults
    """

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Anthropic Workload Identity Federation. Static API keys are unsupported.
    anthropic_federation_rule_id: str = _ssm("anthropic_federation_rule_id")
    anthropic_organization_id: str = _ssm("anthropic_organization_id")
    anthropic_service_account_id: str = _ssm("anthropic_service_account_id")
    anthropic_workspace_id: str = _ssm("anthropic_workspace_id")
    anthropic_identity_token_file: str = "/run/secrets/anthropic/aws-identity-token"
    anthropic_config_directory: str = "/app/data/anthropic-config"

    # Optional OpenAI backend. Set AGENT_PROVIDER=openai and OPENAI_API_KEY to use it.
    openai_api_key: str = _ssm("openai_api_key")

    # Image generation (Nano Banana / Google Gemini)
    google_api_key: str = _ssm("google_api_key")  # Optional - enables imagine tool

    # Database
    database_url: str = _ssm("database_url", "sqlite+aiosqlite:///./data/code_monet.db")
    database_echo: bool = False

    # Auth (required when auth is enabled)
    jwt_secret: str = _ssm("jwt_secret")  # Must be set in production
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 1 day
    jwt_refresh_token_expire_days: int = 365  # 1 year

    # Shared Fenton identity resource-server contract
    identity_issuer: str = "https://identity.dmfenton.net"
    identity_jwks_url: str = "https://identity.dmfenton.net/.well-known/jwks.json"
    identity_audience: str = "codemonet-api"
    identity_client_id: str = "net.dmfenton.codemonet"
    identity_household_id: str = "fenton"

    # Email (SES)
    ses_sender_email: str = "noreply@dmfenton.net"
    ses_region: str = "us-east-1"
    ses_configuration_set: str = "drawing-agent-emails"
    magic_link_expire_minutes: int = 15
    magic_link_base_url: str = "https://monet.dmfenton.net"

    # iOS Universal Links
    apple_team_id: str = _ssm("apple_team_id")  # From SSM or APPLE_TEAM_ID env var
    ios_bundle_id: str = "net.dmfenton.sketchpad"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    dev_mode: bool = True  # Set to False in production; enables live reload
    max_connections_per_user: int = 0  # 0 = unlimited

    # Agent
    agent_interval: int = 60  # UNUSED - kept for backwards compat, agent only runs on explicit wake
    agent_workspace: str = "data/agent_workspace"  # Inside mounted volume for persistence
    workspace_base_dir: str = "data/agent_workspace/users"  # Per-user workspace directories
    max_agent_iterations: int = 5  # max iterations per turn
    quality_gate_auto_revision_turns: int = 3  # extra turns after failed visual critique
    agent_max_tokens: int = 8192  # max tokens for Claude response
    agent_provider: str = _ssm("agent_provider", "anthropic")  # anthropic or openai
    agent_model: str = "claude-sonnet-4-5-20250929"  # Sonnet for visual planning in dev
    agent_model_prod: str = "claude-opus-4-5-20251101"  # Production model
    openai_agent_model: str = "gpt-5-mini"
    openai_agent_model_prod: str = "gpt-5"

    # Agent file logging
    agent_logs_enabled: bool = True  # Enable per-turn agent log files
    agent_logs_max_files: int = 50  # Max log files to keep per user

    # Canvas
    canvas_width: int = 800
    canvas_height: int = 600

    # Drawing (pen plotter motion)
    drawing_fps: int = 30  # frames per second for pen updates
    stroke_delay: float = 0.2  # pause between strokes in seconds
    path_steps_per_unit: float = 0.05  # interpolation density (lower = faster animation)
    travel_speed_multiplier: float = 2.0  # travel faster than drawing (pen up movement)
    pen_settle_delay: float = 0.05  # pause after pen down before moving (servo settling)
    pen_lift_threshold: float = 2.0  # skip pen lift if next path starts within this distance

    # Animation wait (agent pauses while client animates)
    client_animation_fps: int = 240  # client animation frame rate
    animation_wait_buffer_ms: int = 150  # extra buffer for network/fetch latency
    max_animation_wait_s: float = 5.0  # cap to prevent very long waits

    # Limits
    max_stdout_chars: int = 2000  # truncate stdout in messages
    max_stderr_chars: int = 500  # truncate stderr in messages

    # Rate limiting (prevent abuse)
    max_strokes_per_minute: int = 60  # max user strokes per minute
    max_pending_strokes: int = 5000  # max pending strokes queued for animation
    max_workspace_size_bytes: int = 10 * 1024 * 1024  # 10MB max workspace.json size

    # Tracing (OpenTelemetry + X-Ray via ADOT Collector)
    otel_enabled: bool = False  # Enable in production via env var
    otel_service_name: str = "drawing-agent"
    otel_exporter_endpoint: str = "http://otel-collector:4318"  # ADOT Collector OTLP/HTTP
    aws_region: str = "us-east-1"


settings = Settings()
