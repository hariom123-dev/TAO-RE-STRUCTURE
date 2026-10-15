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
import uuid
from typing import AsyncGenerator, Callable, Optional

from backend.api.prometheus_exporter import prometheus_exporter
from backend.caselaw.case_law_store import case_law_store
from backend.config import settings
from backend.guardrails.pre_filter import prompt_pre_filter
from backend.guardrails.receipt_generator import receipt_generator
from backend.guardrails.validator import guardrails_validator
from backend.models import (
    CaseLawPrecedent,
    DebateVerdict,
    GuardrailsResult,
    PipelineEvent,
    PipelineMetrics,
    RiskLevel,
    RoutingDecision,
    TAOReceipt,
    TAORequest,
    TAOResponse,
    Tier1Result,
    Tier2Result,
    Tier3Result,
    TierLevel,
)
from backend.router.complexity_router import classify_query
from backend.state.checkpointer import pipeline_checkpointer
from backend.state.hitl_webhook import hitl_manager
from backend.tier1.compiler import compiler_worker
from backend.tier1.constitution import ConstitutionStore
from backend.tier1.generator import backtrack_and_refine, generate_response
from backend.tier1.process_supervisor import ProcessSupervisor
from backend.tier2.debate_graph import run_debate
from backend.tier3.paraphrase_firewall import paraphrase, verify_semantic_preservation
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
        req_id = request.session_id or str(uuid.uuid4())

        # ── Step 0: Tier -1 Perimeter Pre-Filter (< 0.2ms) ───
        pre_filter_res = prompt_pre_filter.scan(request.query)
        if not pre_filter_res.allowed:
            await self._emit(
                "tier_minus_1_blocked",
                tier=-1,
                data={
                    "violation_type": pre_filter_res.violation_type,
                    "details": pre_filter_res.details,
                    "latency_ms": pre_filter_res.latency_ms,
                },
            )
            metrics.total_latency_ms = round((time.time() - start_time) * 1000, 2)
            metrics.total_tokens = 0
            metrics.tier_executed = TierLevel.TIER_0
            refusal_response = (
                f"🛡️ [TAO Perimeter Intercept - Tier -1]: Request blocked due to {pre_filter_res.violation_type}. "
                f"{pre_filter_res.details}"
            )
            blocked_response = TAOResponse(
                request_id=req_id,
                query=request.query,
                routing=RoutingDecision(tier=TierLevel.TIER_0, risk_level=RiskLevel.HIGH, risk_score=1.0, domain="adversarial"),
                final_response=refusal_response,
                metrics=metrics,
                receipt=None,
            )
            blocked_response.receipt = receipt_generator.generate_receipt(blocked_response)
            prometheus_exporter.record_prompt_injection_block()
            _history.append(blocked_response)
            return blocked_response

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

        # Checkpoint: Router Node
        pipeline_checkpointer.save_checkpoint(
            request_id=req_id,
            node_name="router",
            state_data={"query": request.query, "tier": routing.tier.value, "domain": routing.domain},
            summary=f"Query classified to Tier {routing.tier.value} ({routing.domain})",
        )

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

            # Checkpoint: Tier 1 Process Supervision Node
            pipeline_checkpointer.save_checkpoint(
                request_id=req_id,
                node_name="tier1",
                state_data={
                    "query": request.query,
                    "passed": tier1_result.passed,
                    "iterations": tier1_result.iterations,
                    "final_response": final_response,
                },
                summary=f"Tier 1 Process Supervision ({'Passed' if tier1_result.passed else 'Backtracked'})",
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
                metrics.tokens_saved_by_cache = precedent.tokens_saved
                metrics.usd_saved_by_cache = round(precedent.tokens_saved * 0.00001, 4)

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

                # Pillar 1: Record Hard-Negative & Auto-Compile if High-Confidence Skeptic Win
                if settings.case_law_enabled and tier2_result.verdict == DebateVerdict.SKEPTIC_WINS and tier2_result.judge_confidence >= 0.90:
                    case_law_store.add_hard_negative(
                        query=request.query,
                        flawed_cot=tier1_result.generation.raw_cot if tier1_result else final_response,
                        skeptic_critique=tier2_result.rounds[-1].skeptic_critique.content if tier2_result.rounds else "",
                        judge_verdict=tier2_result.verdict,
                        confidence=tier2_result.judge_confidence,
                        domain=routing.domain,
                    )
                    if compiler_worker.should_compile():
                        compiler_worker.compile_signatures()

                # Trigger HITL escalation if debate was inconclusive / low confidence
                if tier2_result.judge_confidence < settings.tier2_judge_confidence_threshold and tier2_result.total_rounds >= settings.tier2_max_debate_rounds:
                    hitl_payload = hitl_manager.create_payload(
                        request_id=req_id,
                        trigger_reason=f"Debate Inconclusive (Confidence: {tier2_result.judge_confidence:.2f} < {settings.tier2_judge_confidence_threshold:.2f} after {tier2_result.total_rounds} rounds)",
                        severity="WARNING",
                        domain=routing.domain,
                        checkpoint_id="tier2",
                        snippet=final_response,
                    )
                    asyncio.create_task(hitl_manager.dispatch_escalation(hitl_payload))

                # Checkpoint: Tier 2 Debate Node
                pipeline_checkpointer.save_checkpoint(
                    request_id=req_id,
                    node_name="tier2",
                    state_data={
                        "query": request.query,
                        "verdict": tier2_result.verdict.value,
                        "confidence": tier2_result.judge_confidence,
                        "rounds": tier2_result.total_rounds,
                        "final_response": final_response,
                    },
                    summary=f"Tier 2 Debate ({tier2_result.verdict.value}, conf: {tier2_result.judge_confidence:.2f})",
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
                        "weak_verifier_legibility": tier2_result.weak_verifier_legibility_score,
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

                tier3_result = await self._run_tier3(final_response, routing.domain, req_id)

                if tier3_result.paraphrased:
                    final_response = tier3_result.sanitized_text

                metrics.tier3_latency_ms = round((time.time() - t3_start) * 1000, 2)

                # Checkpoint: Tier 3 Stego Node
                pipeline_checkpointer.save_checkpoint(
                    request_id=req_id,
                    node_name="tier3",
                    state_data={
                        "query": request.query,
                        "kl_divergence": tier3_result.stego_analysis.kl_divergence,
                        "alert_triggered": tier3_result.stego_analysis.alert_triggered,
                        "paraphrased": tier3_result.paraphrased,
                        "cusum_drift": tier3_result.cusum_drift_score,
                        "final_response": final_response,
                    },
                    summary=f"Tier 3 Stego Sentinel (KL: {tier3_result.stego_analysis.kl_divergence}, Paraphrased: {tier3_result.paraphrased})",
                )

                await self._emit(
                    "tier3_complete",
                    tier=3,
                    data={
                        "kl_divergence": tier3_result.stego_analysis.kl_divergence,
                        "alert_triggered": tier3_result.stego_analysis.alert_triggered,
                        "paraphrased": tier3_result.paraphrased,
                        "perplexity": tier3_result.stego_analysis.perplexity,
                        "cusum_drift": tier3_result.cusum_drift_score,
                        "semantic_preservation": tier3_result.semantic_preservation_score,
                    },
                )

                if tier3_result.stego_analysis.alert_triggered or tier3_result.cusum_alert_triggered:
                    prometheus_exporter.record_stego_alert(is_cusum=tier3_result.cusum_alert_triggered)
                    try:
                        from backend.state.event_bus import event_bus
                        event_bus.publish_event(
                            event_type="STEGO_DETECTED",
                            severity="CRITICAL",
                            details={
                                "kl_divergence": tier3_result.stego_analysis.kl_divergence,
                                "cusum_drift": tier3_result.cusum_drift_score,
                                "paraphrased": tier3_result.paraphrased,
                            },
                            request_id=req_id,
                        )
                    except Exception:
                        pass
                    hitl_payload = hitl_manager.create_payload(
                        request_id=req_id,
                        trigger_reason=f"Steganography Sentinel Alert (KL: {tier3_result.stego_analysis.kl_divergence:.3f}, CUSUM: {tier3_result.cusum_drift_score:.3f})",
                        severity="CRITICAL",
                        domain=routing.domain,
                        checkpoint_id="tier3",
                        snippet=final_response,
                    )
                    asyncio.create_task(hitl_manager.dispatch_escalation(hitl_payload))

        # ── Step 3: Guardrails AI Output Validation ───────────
        guardrails_result: Optional[GuardrailsResult] = None
        if settings.guardrails_enabled:
            g_start = time.time()
            final_response, guardrails_result = guardrails_validator.validate_and_sanitize(final_response)
            metrics.guardrails_latency_ms = round((time.time() - g_start) * 1000, 2)

            # Checkpoint: Guardrails Node
            pipeline_checkpointer.save_checkpoint(
                request_id=req_id,
                node_name="guardrails",
                state_data={
                    "query": request.query,
                    "passed": guardrails_result.passed,
                    "final_response": final_response,
                },
                summary=f"Output Guardrails ({'Passed' if guardrails_result.passed else 'Flagged'})",
            )

            await self._emit(
                "guardrails_complete",
                data={
                    "passed": guardrails_result.passed,
                    "syntax_valid": guardrails_result.syntax_valid,
                    "pii_detected": guardrails_result.pii_detected,
                },
            )

        metrics.total_latency_ms = round((time.time() - start_time) * 1000, 2)
        metrics.total_cost_usd = round(metrics.total_tokens * 0.00001, 4)
        if routing.tier < 2:
            metrics.usd_saved_by_routing = round(3800 * 0.00001, 4)

        response = TAOResponse(
            request_id=req_id,
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

        # Pillar 7: Zero-Trust Cryptographic Oversight Receipt Attestation
        receipt = receipt_generator.generate_receipt(response)
        response.receipt = receipt

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

        # Record Prometheus Telemetry
        tier_label = f"tier_{routing.tier.value}"
        prometheus_exporter.record_request(tier_label, metrics.total_latency_ms)
        if metrics.usd_saved_by_cache > 0 or metrics.usd_saved_by_routing > 0:
            prometheus_exporter.record_usd_savings(metrics.usd_saved_by_routing, metrics.usd_saved_by_cache)

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

    async def _run_tier3(self, text: str, domain: str, session_id: str = "default") -> Tier3Result:
        """Execute Tier 3: Steganography Detection, CUSUM Drift & Paraphrase Defense."""
        detector = StegoDetector(domain=domain)
        stego_analysis = await detector.analyze(text)

        # Cross-Turn CUSUM drift detection
        cusum_drift, cusum_alert = detector.analyze_session_cusum_drift(session_id, stego_analysis.kl_divergence)
        if cusum_alert:
            stego_analysis.alert_triggered = True

        paraphrased = False
        sanitized_text = text
        similarity = 1.0
        preservation_score = 1.0

        # Paraphrase Defense: triggered on alert OR high-security domains (code/financial)
        is_high_sec = domain in ("code_deployment", "financial", "security")
        if stego_analysis.alert_triggered or is_high_sec:
            sanitized_text, similarity = await paraphrase(text)
            paraphrased = True
            _, preservation_score, _ = verify_semantic_preservation(text, sanitized_text)

        return Tier3Result(
            stego_analysis=stego_analysis,
            paraphrased=paraphrased,
            original_text=text if paraphrased else "",
            sanitized_text=sanitized_text,
            semantic_similarity=similarity,
            cusum_drift_score=cusum_drift,
            cusum_alert_triggered=cusum_alert,
            semantic_preservation_score=preservation_score,
        )

    async def fork_and_replay(
        self,
        original_request_id: str,
        checkpoint_id: str,
        overrides: dict,
    ) -> TAOResponse:
        """
        Pillar 4: LangGraph Time-Travel & Counterfactual Forking.
        Replays pipeline forward from a specified historical checkpoint with parameter overrides.
        """
        chk = pipeline_checkpointer.get_checkpoint(checkpoint_id)
        if not chk:
            raise ValueError(f"Checkpoint '{checkpoint_id}' not found.")

        query = overrides.get("query", chk.state_data.get("query", ""))
        force_tier = overrides.get("force_tier")

        fork_req = TAORequest(
            query=query,
            context=overrides.get("context", ""),
            force_tier=force_tier,
            session_id=str(uuid.uuid4()),
        )

        response = await self.analyze(fork_req)
        response.parent_request_id = original_request_id
        response.checkpoint_id = checkpoint_id
        return response
