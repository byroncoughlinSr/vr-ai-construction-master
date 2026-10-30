from pydantic import AliasChoices, Field
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

    # Total time the planner may spend across Claude → Groq → Ollama → Gemini for one plan.
    # Keep it below the headset's floor-plan request timeout (HouseGenerator.kt,
    # PLAN_CALL_TIMEOUT_S = 240) so the server gives up first and the headset
    # gets a real error instead of a dropped connection.
    planning_timeout_seconds: float = 200.0

    # Claude (primary planner). The key is read from ANTHROPIC_API_KEY or CLAUDE_API_KEY.
    anthropic_api_key: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("anthropic_api_key", "claude_api_key")
    )
    # Sonnet: on the 14-room example ~2 min with one fix round, where Opus took ~3 min
    # for one answer (and timed out at "high"). Opus 5.5 is "claude-opus-5-5".
    anthropic_model: str = "claude-sonnet-5-5"
    # low | medium | high | xhigh | max: how hard Claude thinks about a plan.
    anthropic_effort: str = "medium"
    # The most one Claude answer may take, so a stalled one still leaves Groq a turn.
    anthropic_timeout_seconds: float = 170.0

    # Groq cloud LLM (first fallback)
    groq_api_key: Optional[str] = None
    groq_model: str = "openai/gpt-oss-120b"

    # File paths
    uploads_dir: str = "uploads"
    generated_images_dir: str = "generated_images"
    exports_dir: str = "exports"
    plant_models_dir: str = "plant_models"

    # 3D plant models from photos (plant_model_service.py). "replicate" runs a hosted
    # image-to-3D model (needs REPLICATE_API_TOKEN; the photo is sent to Replicate),
    # "triposr" runs TripoSR on this machine (CPU without CUDA: minutes per model,
    # several GB of RAM), "none" turns it off.
    plant_model_provider: str = "replicate"
    replicate_api_token: Optional[str] = None
    # "owner/name" (its latest version) or "owner/name:version".
    replicate_3d_model: str = "firtoz/trellis"
    # JSON object merged into the model's input, for models with other options.
    replicate_3d_input: Optional[str] = None
    # A clone of https://github.com/VAST-AI-Research/TripoSR with its requirements
    # installed, and the Python that has them (default: this one).
    triposr_dir: Optional[str] = None
    triposr_python: Optional[str] = None
    triposr_mc_resolution: int = 192
    triposr_bake_texture: bool = True
    # Which way is up in the provider's .glb ("y" or "z"); empty: the provider's usual.
    plant_model_up_axis: Optional[str] = None
    plant_model_timeout_seconds: float = 900.0

    # pm-mcp (/development/pm-mcp) holds each project's construction plan:
    # phases, tasks, permits, inspections, budget lines and change orders. It runs
    # beside the backend as an MCP server over HTTP (start_all.sh starts it).
    pm_mcp_url: str = "http://127.0.0.1:8765/mcp"
    pm_mcp_timeout_seconds: float = 15.0

    class Config:
        env_file = ".env"
        case_sensitive = False
        # .env may hold settings of other branches or tools; don't refuse to start over them.
        extra = "ignore"


# Global settings instance
settings = Settings()
