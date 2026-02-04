from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database settings
    database_url: str = "postgresql://vr_admin:SecurePassword123!@localhost:5433/vr_construction"

    # Environment
    environment: str = "development"

    # AI service URLs
    ollama_url: str = "http://localhost:11434"
    gemini_api_key: Optional[str] = None

    # File paths
    uploads_dir: str = "uploads"
    generated_images_dir: str = "generated_images"
    exports_dir: str = "exports"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
