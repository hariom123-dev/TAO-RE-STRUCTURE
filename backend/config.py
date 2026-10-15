"""
TAO Configuration — Environment-driven settings with Pydantic BaseSettings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class TAOSettings(BaseSettings):
    """Central configuration for the TAO architecture."""

    # --- API Keys ---
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    nvidia_nim_api_key: Optional[str] = Field(default=None, alias="NVIDIA_NIM_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")

    # --- Mode ---
    simulation_mode: bool = Field(default=True, alias="SIMULATION_MODE")

    # --- Tier 1: Constitutional Process Supervision ---
    tier1_safety_threshold: float = Field(
        default=0.95,
        alias="TIER1_SAFETY_THRESHOLD",
        description="Min safety score (0-1) per CoT step before backtracking triggers.",
    )

    # --- Tier 2: Adversarial Debate ---
    tier2_max_debate_rounds: int = Field(
        default=3,
        alias="TIER2_MAX_DEBATE_ROUNDS",
        description="Hard limit on debate rounds to prevent runaway token usage.",
    )
    tier2_judge_confidence_threshold: float = Field(
        default=0.9,
        alias="TIER2_JUDGE_CONFIDENCE_THRESHOLD",
        description="Judge confidence above which the debate concludes early.",
    )

    # --- Tier 2: Model Configuration ---
    prover_model: str = Field(default="claude-3-5-sonnet-20241022")
    prover_temperature: float = Field(default=0.7)
    skeptic_model: str = Field(default="gpt-4o")
    skeptic_temperature: float = Field(default=1.0)
    judge_model: str = Field(default="gpt-4o")
    judge_temperature: float = Field(default=0.2)

    # --- Tier 3: Steganography Detection ---
    tier3_kl_divergence_threshold: float = Field(
        default=0.15,
        alias="TIER3_KL_DIVERGENCE_THRESHOLD",
        description="KL divergence above which triggers stego alert (standard tasks).",
    )
    tier3_creative_kl_threshold: float = Field(
        default=0.35,
        alias="TIER3_CREATIVE_KL_THRESHOLD",
        description="Looser threshold for creative writing to reduce false positives.",
    )

    # --- Tier 1: Backtracking / Self-Refine ---
    tier1_max_backtrack_iterations: int = Field(
        default=3,
        alias="TIER1_MAX_BACKTRACK_ITERATIONS",
        description="Max iterations to backtrack and refine violating CoT steps.",
    )

    # --- Case Law Precedent Store (Vector DB) ---
    case_law_enabled: bool = Field(
        default=True,
        alias="CASE_LAW_ENABLED",
        description="Whether to check semantic vector store for past debate rulings.",
    )
    case_law_similarity_threshold: float = Field(
        default=0.78,
        alias="CASE_LAW_SIMILARITY_THRESHOLD",
        description="Cosine similarity threshold to reuse a cached debate verdict.",
    )

    # --- Tier 2: Ensemble Judging & Mitigations ---
    ensemble_judging_enabled: bool = Field(
        default=True,
        alias="ENSEMBLE_JUDGING_ENABLED",
        description="Whether to run a 3-judge panel taking majority vote.",
    )
    cooldown_intervention_enabled: bool = Field(
        default=True,
        alias="COOLDOWN_INTERVENTION_ENABLED",
        description="Whether to inject cool-down grounding prompts when debate polarization/hostility is detected.",
    )

    # --- Output Guardrails ---
    guardrails_enabled: bool = Field(
        default=True,
        alias="GUARDRAILS_ENABLED",
        description="Syntax and PII/safety output validation check before user delivery.",
    )

    # --- Server ---
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


# Singleton
settings = TAOSettings()
