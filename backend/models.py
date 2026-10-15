"""
TAO Data Models — Pydantic models for the entire pipeline.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TierLevel(int, Enum):
    TIER_0 = 0  # Pass-through
    TIER_1 = 1  # Constitutional check
    TIER_2 = 2  # Adversarial debate
    TIER_3 = 3  # Stego detection (added on top of Tier 2)


class ViolationType(str, Enum):
    NONE = "none"
    SYCOPHANCY = "sycophancy"
    HALLUCINATION = "hallucination"
    DECEPTION = "deception"
    TOXIC_COMPLIANCE = "toxic_compliance"
    RULE_LAWYERING = "rule_lawyering"
    BIAS = "bias"
    PRIVACY_LEAK = "privacy_leak"


class ViolationSeverity(str, Enum):
    WARNING = "warning"
    VIOLATION = "violation"
    CRITICAL = "critical"


class DebateVerdict(str, Enum):
    PROVER_WINS = "prover_wins"
    SKEPTIC_WINS = "skeptic_wins"
    INCONCLUSIVE = "inconclusive"
    CONSENSUS = "consensus"


# ─── Routing ────────────────────────────────────────────────────

class RoutingDecision(BaseModel):
    tier: TierLevel
    risk_level: RiskLevel
    risk_score: float = Field(ge=0.0, le=1.0)
    domain: str = "general"
    reasoning: str = ""


# ─── Tier 1: Constitutional ────────────────────────────────────

class ConstitutionalPrinciple(BaseModel):
    id: str
    name: str
    description: str
    severity: ViolationSeverity = ViolationSeverity.VIOLATION


class ConstitutionalViolation(BaseModel):
    principle_id: str
    principle_name: str
    violation_type: ViolationType
    severity: ViolationSeverity
    explanation: str
    correction_guidance: str
    step_index: Optional[int] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class CoTStep(BaseModel):
    index: int
    content: str
    safety_score: float = Field(ge=0.0, le=1.0, default=1.0)
    flagged: bool = False


class GenerationResult(BaseModel):
    model_config = {"protected_namespaces": ()}
    response: str
    cot_steps: list[CoTStep] = []
    raw_cot: str = ""
    reasoning_tokens: int = 0
    completion_tokens: int = 0
    model_used: str = ""


class DSPySignatureOutput(BaseModel):
    """Rigid, type-checked DSPy Signature definition (Table 1 of TAO Report)."""
    context: str
    reasoning_trace: str
    constitution: str
    violation_detected: bool
    violation_type: ViolationType
    correction_guidance: str


class Tier1Result(BaseModel):
    generation: GenerationResult
    violations: list[ConstitutionalViolation] = []
    passed: bool = True
    iterations: int = 1
    reasoning_anomaly: bool = False
    backtrack_history: list[dict[str, Any]] = []
    dspy_signature_output: Optional[DSPySignatureOutput] = None


# ─── Case Law (Vector DB Precedents) ───────────────────────────

class CaseLawPrecedent(BaseModel):
    id: str
    query: str
    domain: str
    verdict: DebateVerdict
    summary_ruling: str
    confidence: float = 0.95
    similarity_score: float = 0.0
    tokens_saved: int = 0
    latency_saved_ms: float = 0.0


# ─── Tier 2: Debate ────────────────────────────────────────────

class DebateArgument(BaseModel):
    model_config = {"protected_namespaces": ()}
    round: int
    agent_role: str  # "prover", "skeptic", "judge", "moderator"
    content: str
    model_used: str = ""
    tokens_used: int = 0


class EnsembleJudgeVote(BaseModel):
    model_config = {"protected_namespaces": ()}
    judge_id: str
    model_name: str
    verdict: DebateVerdict
    confidence: float
    rationale: str = ""


class DebateRound(BaseModel):
    round_number: int
    prover_argument: DebateArgument
    skeptic_critique: DebateArgument
    judge_evaluation: DebateArgument
    judge_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    cooldown_injected: bool = False
    cooldown_prompt: str = ""
    ensemble_evaluations: list[EnsembleJudgeVote] = []


class Tier2Result(BaseModel):
    rounds: list[DebateRound] = []
    verdict: DebateVerdict = DebateVerdict.INCONCLUSIVE
    final_response: str = ""
    judge_confidence: float = 0.0
    swap_test_passed: bool = True
    total_rounds: int = 0
    cooldown_triggered: bool = False
    ensemble_votes: list[EnsembleJudgeVote] = []
    case_law_match: Optional[CaseLawPrecedent] = None


# ─── Tier 3: Steganography ─────────────────────────────────────

class TokenAnalysis(BaseModel):
    token: str
    logprob: float = 0.0
    reference_logprob: float = 0.0
    kl_contribution: float = 0.0


class StegoAnalysis(BaseModel):
    kl_divergence: float = 0.0
    threshold_used: float = 0.15
    alert_triggered: bool = False
    token_analyses: list[TokenAnalysis] = []
    perplexity: float = 0.0
    reference_perplexity: float = 0.0


class Tier3Result(BaseModel):
    stego_analysis: StegoAnalysis = Field(default_factory=StegoAnalysis)
    paraphrased: bool = False
    original_text: str = ""
    sanitized_text: str = ""
    semantic_similarity: float = 1.0


# ─── Output Guardrails ─────────────────────────────────────────

class GuardrailsResult(BaseModel):
    passed: bool = True
    syntax_valid: bool = True
    pii_detected: bool = False
    prompt_leak_detected: bool = False
    checks_run: list[str] = []
    details: list[str] = []


# ─── Pipeline ──────────────────────────────────────────────────

class PipelineMetrics(BaseModel):
    total_latency_ms: float = 0.0
    routing_latency_ms: float = 0.0
    tier1_latency_ms: float = 0.0
    tier2_latency_ms: float = 0.0
    tier3_latency_ms: float = 0.0
    guardrails_latency_ms: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tier_executed: TierLevel = TierLevel.TIER_0
    tokens_saved_by_cache: int = 0


class TAORequest(BaseModel):
    query: str
    context: str = ""
    force_tier: Optional[TierLevel] = None
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class TAOResponse(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    routing: RoutingDecision
    tier1_result: Optional[Tier1Result] = None
    tier2_result: Optional[Tier2Result] = None
    tier3_result: Optional[Tier3Result] = None
    guardrails_result: Optional[GuardrailsResult] = None
    final_response: str = ""
    case_law_applied: bool = False
    reasoning_effort: str = "medium"
    metrics: PipelineMetrics = Field(default_factory=PipelineMetrics)
    timestamp: float = Field(default_factory=time.time)


# ─── WebSocket Events ──────────────────────────────────────────

class PipelineEvent(BaseModel):
    event_type: str  # "routing", "tier1_start", "tier1_complete", "debate_round", etc.
    tier: Optional[int] = None
    data: dict[str, Any] = {}
    timestamp: float = Field(default_factory=time.time)
