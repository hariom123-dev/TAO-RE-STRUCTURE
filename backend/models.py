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
    is_active: bool = True
    weight: float = 1.0


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


class AlternativeBranch(BaseModel):
    branch_id: str
    temperature: float
    cot_steps: list[CoTStep] = []
    cumulative_prm_score: float = 0.0
    passed: bool = True
    pruned: bool = False
    selected: bool = False
    response: str = ""


class GenerationResult(BaseModel):
    model_config = {"protected_namespaces": ()}
    response: str
    cot_steps: list[CoTStep] = []
    raw_cot: str = ""
    reasoning_tokens: int = 0
    completion_tokens: int = 0
    model_used: str = ""
    alternative_branches: list[AlternativeBranch] = []
    prm_search_trajectory: list[dict[str, Any]] = []


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
    first_flawed_step_index: Optional[int] = None
    search_strategy: str = "linear"  # "linear" or "omega_prm_binary_search"


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
    hard_negative: bool = False
    compiled_to_dspy: bool = False


# ─── Tier 2: Debate ────────────────────────────────────────────

class DebateArgument(BaseModel):
    model_config = {"protected_namespaces": ()}
    round: int
    agent_role: str  # "prover", "skeptic", "judge", "moderator"
    content: str
    model_used: str = ""
    tokens_used: int = 0
    tool_evidences: list[dict[str, Any]] = []


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
    weak_verifier_legibility_score: float = 1.0
    collusion_detected: bool = False
    skeptic_provider_swapped: bool = False


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
    cusum_drift_score: float = 0.0
    cusum_alert_triggered: bool = False
    semantic_preservation_score: float = 1.0


# ─── Output Guardrails ─────────────────────────────────────────

class GuardrailsResult(BaseModel):
    passed: bool = True
    syntax_valid: bool = True
    pii_detected: bool = False
    prompt_leak_detected: bool = False
    checks_run: list[str] = []
    details: list[str] = []


# ─── Zero-Trust Cryptographic Receipts ─────────────────────────

class TAOReceipt(BaseModel):
    receipt_id: str = Field(default_factory=lambda: f"rcpt_{uuid.uuid4().hex[:12]}")
    request_id: str
    timestamp: float = Field(default_factory=time.time)
    root_hash: str
    merkle_proof: list[str] = []
    node_hashes: dict[str, str] = {}
    signature: str = ""
    signer_id: str = "tao_safety_gateway_v2"
    algorithm: str = "HMAC-SHA256"
    verified: bool = True


class ReceiptVerificationResult(BaseModel):
    valid: bool
    receipt_id: str
    computed_root: str
    stored_root: str
    signature_valid: bool
    details: list[str] = []


# ─── Checkpoint & Time-Travel Models ───────────────────────────

class CheckpointSnapshot(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: f"chk_{uuid.uuid4().hex[:10]}")
    request_id: str
    node_name: str
    timestamp: float = Field(default_factory=time.time)
    summary: str = ""
    state_data: dict[str, Any] = {}


class ForkRequest(BaseModel):
    original_request_id: str
    checkpoint_id: str
    overrides: dict[str, Any] = {}


class ReceiptVerifyRequest(BaseModel):
    receipt: TAOReceipt


class RedTeamRequest(BaseModel):
    task: str = "medical_sycophancy"  # "medical_sycophancy", "smart_contract_backdoor", "acrostic_stego"
    user_query: str = ""
    target_flaw: str = ""
    difficulty: int = 3


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
    usd_saved_by_cache: float = 0.0
    usd_saved_by_routing: float = 0.0


class TAORequest(BaseModel):
    query: str
    context: str = ""
    force_tier: Optional[TierLevel] = None
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_api_keys: Optional[dict[str, str]] = None


class TAOResponse(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_request_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    query: str
    routing: RoutingDecision
    tier1_result: Optional[Tier1Result] = None
    tier2_result: Optional[Tier2Result] = None
    tier3_result: Optional[Tier3Result] = None
    guardrails_result: Optional[GuardrailsResult] = None
    receipt: Optional[TAOReceipt] = None
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
