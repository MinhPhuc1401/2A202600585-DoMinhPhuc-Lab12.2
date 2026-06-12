"""Production config — 12-Factor: tất cả từ environment variables."""
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def _infer_provider(model: str) -> str:
    normalized = model.lower()
    if normalized.startswith("gemini"):
        return "gemini"
    if normalized.startswith("gpt") or normalized.startswith("o1") or normalized.startswith("o3"):
        return "openai"
    return "custom"

@dataclass
class Settings:
    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    # App
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Production AI Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    # LLM general settings
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", ""))
    llm_temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0")))

    # Security
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-jwt-secret"))
    allowed_origins: list = field(
        default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(",")
    )

    # Rate limiting
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
    )

    # Budget
    daily_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "5.0"))
    )

    # Storage
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))

    # Provider custom LLM settings
    custom_llm_base_url: str = field(default_factory=lambda: os.getenv("CUSTOM_LLM_BASE_URL", ""))
    custom_llm_api_key: str = field(default_factory=lambda: os.getenv("CUSTOM_LLM_API_KEY", ""))
    custom_llm_model: str = field(default_factory=lambda: os.getenv("CUSTOM_LLM_MODEL", ""))

    # RAG / Embedding settings
    embedding_model_name: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    top_k: int = field(default_factory=lambda: int(os.getenv("RAG_TOP_K", "4")))

    # API keys for other providers
    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
    openrouter_site_url: str = field(default_factory=lambda: os.getenv("OPENROUTER_SITE_URL", ""))
    openrouter_app_name: str = field(default_factory=lambda: os.getenv("OPENROUTER_APP_NAME", ""))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

    # Day09 Agent Compatibility Properties
    @property
    def provider(self) -> str:
        return self.llm_provider or _infer_provider(self.llm_model)

    @property
    def model(self) -> str:
        return self.llm_model

    @property
    def temperature(self) -> float:
        return self.llm_temperature

    @property
    def root_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def policy_path(self) -> Path:
        return self.root_dir / "data" / "policy_mock_vi.md"

    @property
    def orders_path(self) -> Path:
        return self.root_dir / "data" / "order_customer_mock_data.json"

    @property
    def chroma_dir(self) -> Path:
        return self.root_dir / "app" / ".chroma"

    @property
    def traces_dir(self) -> Path:
        return self.root_dir / "app" / "artifacts" / "traces"

    def validate(self):
        logger = logging.getLogger(__name__)
        if self.environment == "production":
            if self.agent_api_key == "dev-key-change-me":
                raise ValueError("AGENT_API_KEY must be set in production!")
            if self.jwt_secret == "dev-jwt-secret":
                raise ValueError("JWT_SECRET must be set in production!")
        # If provider is custom, validate base url and api key
        if self.provider == "custom":
            if not self.custom_llm_base_url:
                logger.warning("CUSTOM_LLM_BASE_URL not set for custom provider")
            if not self.custom_llm_api_key:
                logger.warning("CUSTOM_LLM_API_KEY not set for custom provider")
        elif not self.openai_api_key and self.provider == "openai":
            logger.warning("OPENAI_API_KEY not set — using mock LLM")
        return self

settings = Settings().validate()
