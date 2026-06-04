"""
Centralized application configuration using pydantic-settings.

All environment variables, timeouts, model names, and constants are managed here.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- API Keys ---
    gemini_api_key: str = Field(..., description="Google Gemini API key")

    # --- Server ---
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8080, description="Server bind port")
    log_level: str = Field(default="INFO", description="Logging level")
    node_env: str = Field(default="development", alias="NODE_ENV", description="Environment name")

    # --- Gemini Models ---
    generation_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model for text generation",
    )
    embedding_model: str = Field(
        default="embedding-001",
        description="Gemini model for embeddings",
    )

    # --- Session Management ---
    session_timeout_minutes: int = Field(
        default=20,
        description="Inactive session cleanup timeout in minutes",
    )
    session_cleanup_interval_minutes: int = Field(
        default=5,
        description="Interval between inactive session cleanup sweeps",
    )
    heartbeat_interval_seconds: int = Field(
        default=30,
        description="WebSocket heartbeat ping interval",
    )

    # --- Audio Processing ---
    max_audio_duration_seconds: int = Field(
        default=30,
        description="Maximum audio recording duration",
    )

    # --- WebSocket ---
    max_payload_bytes: int = Field(
        default=10 * 1024 * 1024,  # 10 MB
        description="Maximum WebSocket payload size",
    )

    # --- Knowledge Base ---
    knowledge_base_path: str = Field(
        default="data/krishna-knowledge-base.json",
        description="Path to the knowledge base JSON file (relative to backend/)",
    )
    embedding_rate_limit_ms: int = Field(
        default=100,
        description="Delay between embedding API calls to avoid rate limits",
    )

    # --- Application Metadata ---
    app_name: str = "Paarth - Krishna AI Voice Assistant"
    app_version: str = "2.0.0"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


# Singleton settings instance — import this throughout the app.
settings = Settings()
