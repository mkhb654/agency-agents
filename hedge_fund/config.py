"""Application configuration using pydantic-settings.

All settings can be overridden via environment variables or a .env file.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Supported LLM provider backends."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"


# ---------------------------------------------------------------------------
# Default model identifiers per provider
# ---------------------------------------------------------------------------
DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.OPENAI: "gpt-4.1",
    LLMProvider.ANTHROPIC: "claude-sonnet-4-20250514",
    LLMProvider.GOOGLE: "gemini-2.0-flash",
    LLMProvider.GROQ: "llama-3.3-70b-versatile",
    LLMProvider.DEEPSEEK: "deepseek-chat",
    LLMProvider.OLLAMA: "llama3.2",
}


class Settings(BaseSettings):
    """Central configuration for the hedge fund application.

    Values are loaded in order: constructor kwargs -> environment variables -> .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # LLM settings
    # ------------------------------------------------------------------
    llm_provider: LLMProvider = Field(
        default=LLMProvider.OPENAI,
        description="Which LLM provider to use for agent inference.",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Model identifier. When None the default for the chosen provider is used.",
    )
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for LLM calls.",
    )

    # ------------------------------------------------------------------
    # API keys (only the one for the selected provider needs to be set)
    # ------------------------------------------------------------------
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key.")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key.")
    google_api_key: Optional[str] = Field(default=None, description="Google AI API key.")
    groq_api_key: Optional[str] = Field(default=None, description="Groq API key.")
    deepseek_api_key: Optional[str] = Field(default=None, description="DeepSeek API key.")

    # ------------------------------------------------------------------
    # Financial data
    # ------------------------------------------------------------------
    financial_datasets_api_key: Optional[str] = Field(
        default=None,
        description="API key for https://api.financialdatasets.ai.",
    )

    # ------------------------------------------------------------------
    # Portfolio defaults
    # ------------------------------------------------------------------
    initial_cash: float = Field(
        default=100_000.0,
        gt=0,
        description="Starting cash balance in USD.",
    )
    margin_requirement: float = Field(
        default=0.50,
        gt=0.0,
        le=1.0,
        description="Margin requirement as a fraction (e.g. 0.50 = 50%).",
    )
    max_position_size_pct: float = Field(
        default=0.25,
        gt=0.0,
        le=1.0,
        description="Maximum single-position size as a fraction of total portfolio value.",
    )
    risk_free_rate: float = Field(
        default=0.045,
        ge=0.0,
        description="Annualised risk-free rate used for Sharpe / pricing calculations.",
    )

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    cache_ttl_seconds: int = Field(
        default=3600,
        ge=0,
        description="Default TTL for in-memory cache entries (seconds). 0 = no caching.",
    )

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", description="FastAPI bind host.")
    api_port: int = Field(default=8000, ge=1, le=65535, description="FastAPI bind port.")

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    database_url: str = Field(
        default="sqlite+aiosqlite:///./hedge_fund.db",
        description="SQLAlchemy database connection string.",
    )

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------
    @property
    def resolved_model(self) -> str:
        """Return the model identifier, falling back to the provider default."""
        if self.llm_model is not None:
            return self.llm_model
        return DEFAULT_MODELS[self.llm_provider]

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalise_provider(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    def get_api_key_for_provider(self, provider: Optional[LLMProvider] = None) -> Optional[str]:
        """Look up the API key for the given (or configured) provider."""
        p = provider or self.llm_provider
        mapping: dict[LLMProvider, Optional[str]] = {
            LLMProvider.OPENAI: self.openai_api_key,
            LLMProvider.ANTHROPIC: self.anthropic_api_key,
            LLMProvider.GOOGLE: self.google_api_key,
            LLMProvider.GROQ: self.groq_api_key,
            LLMProvider.DEEPSEEK: self.deepseek_api_key,
            LLMProvider.OLLAMA: None,  # Ollama is local; no key needed.
        }
        return mapping.get(p)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
