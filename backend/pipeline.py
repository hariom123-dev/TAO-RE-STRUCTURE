"""
Pipeline Orchestrator — End-to-end TAO pipeline.

Flow:
  1. Receive query → Complexity Router → get tier assignment & reasoning effort
  2. Tier 0: Direct pass-through (no oversight)
  3. Tier 1: Generate → Process Supervise → DSPy Constitutional Check → Backtracking / Self-Refine loop
  4. Case Law Check: Vector Store precedent search (bypasses 6.87x debate cost if precedent exists)
  5. Tier 2: Adversarial Debate (Prover vs Skeptic vs Ensemble Judge) + Swap-Test + Cool-Down grounding
  6. Tier 3: Stego Detection (Perplexity & KL Divergence) + Paraphrase Firewall (triggered by High Risk or Tier 1 Anomaly)
  7. Output Guardrails: Syntax validation, PII redaction, and prompt injection/leak checks
"""

import asyncio
import time
from typing import AsyncGenerator, Callable, Optional

from backend.caselaw.case_law_store import case_law_store
from backend.config import settings
from backend.guardrails.validator import guardrails_validator
from backend.models import (
    CaseLawPrecedent,
    DebateVerdict,
    GuardrailsResult,
    PipelineEvent,
    PipelineMetrics,
    TAORequest,
    TAOResponse,
    Tier1Result,
    Tier2Result,
    Tier3Result,
    TierLevel,
)
from backend.router.complexity_router import classify_query
from backend.tier1.constitution import ConstitutionStore
from backend.tier1.generator import backtrack_and_refine, generate_response
from backend.tier1.process_supervisor import ProcessSupervisor
from backend.tier2.debate_graph import run_debate
from backend.tier3.paraphrase_firewall import paraphrase
from backend.tier3.stego_detector import StegoDetector


# ─── Pipeline History (in-memory) ──────────────────────────────
_history: list[TAOResponse] = []


def get_history() -> list[TAOResponse]:
    return _history


class TAOPipeline:
    """
    Orchestrates the full Tiered Adversarial Oversight (TAO) architecture.

    Supports:
    - Event streaming via callback for WebSocket/SSE
    - Force-tier override for testing
    - Automated Process Supervision with Backtracking / Self-Refine
    - Vector Store Case Law Precedent Caching
    - 3-Judge Ensemble Voting & Cool-Down Polarization Interventions
    - Context-Aware Stego Detection & Paraphrase Firewall
    - Output Guardrails Syntax & PII Validation
    - Full metrics collection at each stage
    """

    def __init__(self, event_callback: Optional[Callable] = None):
        self.constitution = ConstitutionStore()
        self.supervisor = ProcessSupervisor(self.constitution)
        self.event_callback = event_callback

    async def _emit(self, event_type: str, tier: Optional[int] = None, data: dict = None):
        """Emit a pipeline event (for WebSocket streaming)."""
        event = PipelineEvent(
            event_type=event_type,
            tier=tier,
            data=data or {},
        )
        if self.event_callback:
            await self.event_callback(event)

    async def analyze(self, request: TAORequest) -> TAOResponse:
        """Run the full TAO pipeline on a query."""
        start_time = time.time()
        metrics = PipelineMetrics()

        # ── Step 1: Route & Complexity Triage ─────────────────
        await self._emit("routing", data={"query": request.query})
        route_start = time.time()

        if request.force_tier is not None:
            routing = classify_query(request.query)
            routing.tier = request.force_tier
        else:
            routing = classify_query(request.query)

        metrics.routing_latency_ms = round((time.time() - route_start) * 1000, 2)
        metrics.tier_executed = routing.tier

        # Dynamic Reasoning Effort tuning (Section 6.4)
        if routing.tier.value >= TierLevel.TIER_2.value:
            reasoning_effort = "high"
        elif routing.tier == TierLevel.TIER_1:
            reasoning_effort = "medium"
        else:
            reasoning_effort = "low"

        await self._emit(
            "routing_complete",
            data={
                "tier": routing.tier.value,
                "risk_level": routing.risk_level.value,
                "risk_score": routing.risk_score,
                "domain": routing.domain,
                "reasoning": routing.reasoning,
                "reasoning_effort": reasoning_effort,
            },
        )

        # ── Step 2: Execute Appropriate Tiers ─────────────────
        tier1_result: Optional[Tier1Result] = None
        tier2_result: Optional[Tier2Result] = None
        tier3_result: Optional[Tier3Result] = None
        final_response = ""
        case_law_applied = False

        # ── TIER 1: Constitutional Process Supervision ────────
        if routing.tier.value >= TierLevel.TIER_1.value or routing.tier == TierLevel.TIER_0:
            await self._emit("tier1_start", tier=1)
            t1_start = time.time()

            tier1_result = await self._run_tier1_with_backtracking(
                request.query, routing.risk_level.value, reasoning_effort
            )
            final_response = tier1_result.generation.response

            metrics.tier1_latency_ms = round((time.time() - t1_start) * 1000, 2)
            metrics.total_tokens += (
                tier1_result.generation.reasoning_tokens + tier1_result.generation.completion_tokens
            )

            await self._emit(
                "tier1_complete",
                tier=1,
                data={
                    "passed": tier1_result.passed,
                    "violations": len(tier1_result.violations),
                    "reasoning_anomaly": tier1_result.reasoning_anomaly,
                    "cot_steps": len(tier1_result.generation.cot_steps),
                    "iterations": tier1_result.iterations,
                    "backtracks": len(tier1_result.backtrack_history),
                },
            )

        # ── TIER 2: Adversarial Debate / Case Law Precedent ────
        if routing.tier.value >= TierLevel.TIER_2.value:
            t2_start = time.time()

            # Check Case Law Precedent database first (Section 6.1)
            precedent: Optional[CaseLawPrecedent] = None
            if settings.case_law_enabled:
                precedent = case_law_store.search_precedent(request.query, routing.domain)

            if precedent:
                # Precedent match found! Retrieve ruling and avoid 6.87x debate cost
                case_law_applied = True
                metrics.tokens_saved_by_cache = precedent.tokens_saved
                metrics.tier2_latency_ms = round((time.time() - t2_start) * 1000, 2)

                tier2_result = Tier2Result(
                    rounds=[],
                    verdict=precedent.verdict,
                    final_response=final_response,
                    judge_confidence=precedent.confidence,
                    swap_test_passed=True,
                    total_rounds=0,
                    case_law_match=precedent,
                )

                await self._emit(
                    "case_law_hit",
                    tier=2,
                    data={
                        "precedent_id": precedent.id,
                        "similarity": precedent.similarity_score,
                        "verdict": precedent.verdict.value,
                        "tokens_saved": precedent.tokens_saved,
                    },
                )
                await self._emit(
                    "tier2_complete",
                    tier=2,
                    data={
                        "rounds": 0,
                        "verdict": precedent.verdict.value,
                        "judge_confidence": precedent.confidence,
                        "case_law_used": True,
                    },
                )
            else:
                # Run full multi-agent debate
                await self._emit("tier2_start", tier=2)
                tier2_result = await self._run_tier2(
                    request.query, final_response, request.context
                )

                if tier2_result.final_response:
                    final_response = tier2_result.final_response

                metrics.tier2_latency_ms = round((time.time() - t2_start) * 1000, 2)
                for r in tier2_result.rounds:
                    metrics.total_tokens += (
                        r.prover_argument.tokens_used
                        + r.skeptic_critique.tokens_used
                        + r.judge_evaluation.tokens_used
                    )

                # Store newly established debate verdict in Case Law
                if settings.case_law_enabled and tier2_result.judge_confidence >= 0.85:
                    case_law_store.store_ruling(
                        query=request.query,
                        domain=routing.domain,
                        verdict=tier2_result.verdict,
                        summary_ruling=f"Ruling for {routing.domain}: {tier2_result.verdict.value.upper()}",
                        confidence=tier2_result.judge_confidence,
                    )

                await self._emit(
                    "tier2_complete",
                    tier=2,
                    data={
                        "rounds": tier2_result.total_rounds,
                        "verdict": tier2_result.verdict.value,
                        "judge_confidence": tier2_result.judge_confidence,
                        "swap_test_passed": tier2_result.swap_test_passed,
                        "cooldown_triggered": tier2_result.cooldown_triggered,
                        "ensemble_votes_count": len(tier2_result.ensemble_votes),
                    },
                )

            # ── TIER 3: Steganography Detection & Paraphrase Firewall ─
            # Tier 3 runs alongside Tier 2, or whenever Tier 1 flags a reasoning token anomaly
            should_run_tier3 = (routing.tier.value >= TierLevel.TIER_2.value) or (
                tier1_result and tier1_result.reasoning_anomaly
            )

            if should_run_tier3:
                await self._emit("tier3_start", tier=3)
                t3_start = time.time()

                tier3_result = await self._run_tier3(final_response, routing.domain)

                if tier3_result.paraphrased:
                    final_response = tier3_result.sanitized_text

                metrics.tier3_latency_ms = round((time.time() - t3_start) * 1000, 2)

                await self._emit(
                    "tier3_complete",
                    tier=3,
                    data={
                        "kl_divergence": tier3_result.stego_analysis.kl_divergence,
                        "alert_triggered": tier3_result.stego_analysis.alert_triggered,
                        "paraphrased": tier3_result.paraphrased,
                        "perplexity": tier3_result.stego_analysis.perplexity,
                    },
                )

        # ── Step 3: Guardrails AI Output Validation ───────────
        guardrails_result: Optional[GuardrailsResult] = None
        if settings.guardrails_enabled:
            g_start = time.time()
            final_response, guardrails_result = guardrails_validator.validate_and_sanitize(final_response)
            metrics.guardrails_latency_ms = round((time.time() - g_start) * 1000, 2)
            await self._emit(
                "guardrails_complete",
                data={
                    "passed": guardrails_result.passed,
                    "syntax_valid": guardrails_result.syntax_valid,
                    "pii_detected": guardrails_result.pii_detected,
                },
            )

        # ── Step 4: Finalize Metrics & Response ───────────────
        metrics.total_latency_ms = round((time.time() - start_time) * 1000, 2)
        metrics.total_cost_usd = round(metrics.total_tokens * 0.00001, 4)

        response = TAOResponse(
            query=request.query,
            routing=routing,
            tier1_result=tier1_result,
            tier2_result=tier2_result,
            tier3_result=tier3_result,
            guardrails_result=guardrails_result,
            final_response=final_response,
            case_law_applied=case_law_applied,
            reasoning_effort=reasoning_effort,
            metrics=metrics,
        )

        await self._emit(
            "pipeline_complete",
            data={
                "tier_executed": routing.tier.value,
                "total_latency_ms": metrics.total_latency_ms,
                "total_tokens": metrics.total_tokens,
                "total_cost_usd": metrics.total_cost_usd,
                "case_law_applied": case_law_applied,
            },
        )

        # Store in history
        _history.append(response)
        if len(_history) > 100:
            _history.pop(0)

        return response

    async def _run_tier1_with_backtracking(
        self, query: str, risk_level: str, reasoning_effort: str
    ) -> Tier1Result:
        """
        Execute Tier 1 with Automated Process Supervision & Backtracking (Section 3.2).
        If any step score drops below threshold, backtracks and regenerates that step.
        """
        generation = await generate_response(
            query, risk_level=risk_level, reasoning_effort=reasoning_effort
        )
        result = self.supervisor.evaluate(generation, query)

        iteration = 1
        backtrack_history = []
        max_iterations = settings.tier1_max_backtrack_iterations

        # Backtracking loop (Section 3.2: Self-Refine loop for low-level reward hacking)
        while not result.passed and iteration < max_iterations:
            # Locate first failing step index
            failing_idx = 0
            guidance = "Regenerate with objective reasoning."
            if result.violations:
                failing_idx = result.violations[0].step_index or 0
                guidance = result.violations[0].correction_guidance

            backtrack_history.append({
                "iteration": iteration,
                "failing_step_index": failing_idx,
                "guidance": guidance,
                "timestamp": time.time(),
            })

            await self._emit(
                "tier1_backtrack",
                tier=1,
                data={
                    "iteration": iteration,
                    "failing_step_index": failing_idx,
                    "guidance": guidance,
                },
            )

            # Backtrack and regenerate reasoning from failing step
            refined_gen = await backtrack_and_refine(
                query=query,
                previous_generation=generation,
                failing_step_index=failing_idx,
                correction_guidance=guidance,
                constitution_text=self.constitution.format_for_prompt(),
            )

            generation = refined_gen
            result = self.supervisor.evaluate(generation, query)
            iteration += 1

        result.iterations = iteration
        result.backtrack_history = backtrack_history
        return result

    async def _run_tier2(self, query: str, initial_response: str, context: str) -> Tier2Result:
        """Execute Tier 2: Multi-Agent Adversarial Debate with Ensemble Judging."""
        result = await run_debate(
            context=context or "Standard analysis context.",
            initial_response=initial_response,
            query=query,
        )
        return result

    async def _run_tier3(self, text: str, domain: str) -> Tier3Result:
        """Execute Tier 3: Steganography Detection & Paraphrase Defense."""
        detector = StegoDetector(domain=domain)
        stego_analysis = await detector.analyze(text)

        paraphrased = False
        sanitized_text = text
        similarity = 1.0

        # Paraphrase Defense: triggered on alert OR high-security domains (code/financial)
        is_high_sec = domain in ("code_deployment", "financial", "security")
        if stego_analysis.alert_triggered or is_high_sec:
            sanitized_text, similarity = await paraphrase(text)
            paraphrased = True

        return Tier3Result(
            stego_analysis=stego_analysis,
            paraphrased=paraphrased,
            original_text=text if paraphrased else "",
            sanitized_text=sanitized_text,
            semantic_similarity=similarity,
        )
