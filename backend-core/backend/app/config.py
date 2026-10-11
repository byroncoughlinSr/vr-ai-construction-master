from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database settings
    database_url: str = "postgresql://vr_admin:SecurePassword123!@localhost:5433/vr_construction"

    # Environment
    environment: str = "development"

    # HTTP security. Lists are JSON in .env, e.g. CORS_ORIGINS='["http://192.168.4.249:3001"]'.
    # "*" is fine on a home LAN; set real origins/hostnames before exposing the server.
    cors_origins: List[str] = ["*"]
    allowed_hosts: List[str] = ["*"]
    # When set, collaboration-room WebSockets must pass ?token=<this value>.
    collab_token: Optional[str] = None

    # Log every SQL statement (very noisy).
    sql_echo: bool = False

    # AI service URLs
    ollama_url: str = "http://localhost:11434"
    # Use the 8b tag exactly; llama3.1:latest was getting OOM-killed.
    ollama_model: str = "llama3.1:8b"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"

    # Total time the planner may spend across Groq → Ollama → Gemini for one plan.
    # Keep it below the headset's floor-plan request timeout (HouseGenerator.kt,
    # PLAN_CALL_TIMEOUT_S = 240) so the server gives up first and the headset
    # gets a real error instead of a dropped connection.
    planning_timeout_seconds: float = 200.0

    # Groq cloud LLM (primary planner)
    groq_api_key: Optional[str] = None
    groq_model: str = "openai/gpt-oss-120b"

    # File paths
    uploads_dir: str = "uploads"
    generated_images_dir: str = "generated_images"
    exports_dir: str = "exports"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
