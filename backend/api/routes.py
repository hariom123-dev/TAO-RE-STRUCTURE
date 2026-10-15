import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect
from backend.models import (
    ConstitutionalPrinciple,
    DebateVerdict,
    ForkRequest,
    PipelineEvent,
    ReceiptVerificationResult,
    ReceiptVerifyRequest,
    RedTeamRequest,
    TAORequest,
    TAOResponse,
    TierLevel,
)
from backend.pipeline import TAOPipeline, get_history
from backend.tier1.constitution import ConstitutionStore, DEFAULT_CONSTITUTION
from backend.tier1.compiler import compiler_worker
from backend.guardrails.receipt_generator import receipt_generator
from backend.state.checkpointer import pipeline_checkpointer
from backend.redteam.houdini_agent import houdini_agent
from backend.config import settings

router = APIRouter()

# Shared constitution store
_constitution_store = ConstitutionStore()


@router.post("/api/analyze", response_model=TAOResponse)
async def analyze_query(
    request: TAORequest,
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
    x_ollama_base_url: Optional[str] = Header(None, alias="X-Ollama-Base-URL"),
) -> TAOResponse:
    """
    Submit a query through the TAO pipeline.

    The query is routed through the complexity router and
    processed by the appropriate tiers.
    """
    if request.client_api_keys is None:
        request.client_api_keys = {}
    if x_openai_key and "openai" not in request.client_api_keys:
        request.client_api_keys["openai"] = x_openai_key
    if x_anthropic_key and "anthropic" not in request.client_api_keys:
        request.client_api_keys["anthropic"] = x_anthropic_key
    if x_ollama_base_url and "ollama" not in request.client_api_keys:
        request.client_api_keys["ollama"] = x_ollama_base_url
    if not request.client_api_keys:
        request.client_api_keys = None

    pipeline = TAOPipeline()
    result = await pipeline.analyze(request)
    return result


@router.get("/api/constitution")
async def get_constitution():
    """Get the active constitutional principles."""
    return {
        "principles": [p.model_dump() for p in _constitution_store.principles],
        "total": len(_constitution_store.principles),
    }


@router.post("/api/constitution")
async def update_constitution(principle: ConstitutionalPrinciple):
    """Add or update a constitutional principle."""
    _constitution_store.add(principle)
    return {"status": "updated", "principle": principle.model_dump()}


@router.get("/api/history")
async def get_analysis_history(limit: int = 20):
    """Get past analyses with debate transcripts."""
    history = get_history()
    return {
        "analyses": [r.model_dump() for r in history[-limit:]],
        "total": len(history),
    }


from backend.caselaw.case_law_store import case_law_store


@router.get("/api/caselaw")
async def get_case_law():
    """Get precedents stored in the Case Law vector database."""
    precedents = case_law_store.get_all()
    return {
        "precedents": [p.model_dump() for p in precedents],
        "total": len(precedents),
    }


@router.get("/api/config")
async def get_config():
    """Get current TAO configuration (non-sensitive)."""
    return {
        "simulation_mode": settings.simulation_mode,
        "tier1_safety_threshold": settings.tier1_safety_threshold,
        "tier1_max_backtrack_iterations": settings.tier1_max_backtrack_iterations,
        "tier2_max_debate_rounds": settings.tier2_max_debate_rounds,
        "tier2_judge_confidence_threshold": settings.tier2_judge_confidence_threshold,
        "tier3_kl_divergence_threshold": settings.tier3_kl_divergence_threshold,
        "tier3_creative_kl_threshold": settings.tier3_creative_kl_threshold,
        "case_law_enabled": settings.case_law_enabled,
        "ensemble_judging_enabled": settings.ensemble_judging_enabled,
        "guardrails_enabled": settings.guardrails_enabled,
        "has_openai_key": settings.openai_api_key is not None and len(settings.openai_api_key or "") > 5,
        "has_anthropic_key": settings.anthropic_api_key is not None and len(settings.anthropic_api_key or "") > 5,
    }


@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0", "architecture": "TAO"}


# ─── Pillar 4: LangGraph Time-Travel & Counterfactual Forking ──

@router.post("/api/pipeline/fork", response_model=TAOResponse)
async def fork_pipeline(request: ForkRequest) -> TAOResponse:
    """Replay pipeline execution forward from a historical state checkpoint with overrides."""
    pipeline = TAOPipeline()
    return await pipeline.fork_and_replay(
        original_request_id=request.original_request_id,
        checkpoint_id=request.checkpoint_id,
        overrides=request.overrides,
    )


@router.get("/api/pipeline/checkpoints/{request_id}")
async def get_checkpoints(request_id: str):
    """Retrieve historical state checkpoints recorded for a specific request ID."""
    checkpoints = pipeline_checkpointer.get_checkpoints_for_request(request_id)
    return {
        "request_id": request_id,
        "checkpoints": [c.model_dump() for c in checkpoints],
        "total": len(checkpoints),
    }


# ─── Pillar 7: Zero-Trust Cryptographic Oversight Receipts ─────

@router.post("/api/verify-receipt", response_model=ReceiptVerificationResult)
async def verify_receipt(request: ReceiptVerifyRequest) -> ReceiptVerificationResult:
    """Verify cryptographic authenticity and Merkle tree root of an execution receipt."""
    return receipt_generator.verify_receipt(request.receipt)


# ─── Pillar 1: DSPy Teleprompter Distillation Compiler ─────────

@router.get("/api/compiler/status")
async def compiler_status():
    """Get telemetry status of the DSPy distillation pipeline."""
    return compiler_worker.get_status()


@router.post("/api/compiler/compile")
async def trigger_compilation():
    """Manually trigger compilation of accumulated Case Law hard negatives."""
    return compiler_worker.compile_signatures(force=True)


# ─── Pillar 6: Live Guard vs Houdini Red-Team Arena ────────────

@router.post("/api/redteam/run")
async def run_redteam_attack(request: RedTeamRequest):
    """Generate an adversarial Houdini attack and test TAO's Guard Slope."""
    attack = houdini_agent.generate_attack(
        task=request.task,
        difficulty=request.difficulty,
        custom_query=request.user_query or None,
    )
    pipeline = TAOPipeline()
    tao_req = TAORequest(query=attack["query"])
    response = await pipeline.analyze(tao_req)

    tier1_caught = (response.tier1_result is not None and not response.tier1_result.passed)
    tier2_caught = (response.tier2_result is not None and response.tier2_result.verdict == DebateVerdict.SKEPTIC_WINS)
    tier3_caught = (response.tier3_result is not None and response.tier3_result.stego_analysis.alert_triggered)

    flaw_caught = tier1_caught or tier2_caught or tier3_caught
    guard_metrics = houdini_agent.compute_guard_slope([
        {"difficulty": request.difficulty, "flaw_caught": flaw_caught}
    ])

    return {
        "attack_metadata": attack,
        "flaw_caught": flaw_caught,
        "caught_by_tiers": {
            "tier1": tier1_caught,
            "tier2": tier2_caught,
            "tier3": tier3_caught,
        },
        "guard_metrics": guard_metrics,
        "pipeline_response": response.model_dump(),
    }


# ─── WebSocket for streaming pipeline events ──────────────────

@router.websocket("/ws/pipeline")
async def pipeline_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time pipeline event streaming.

    Send a JSON query to start analysis:
      {"query": "your query here", "force_tier": 2}

    Receive events as the pipeline progresses through each tier.
    """
    await websocket.accept()

    try:
        while True:
            # Wait for a query
            data = await websocket.receive_text()
            try:
                request_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})
                continue

            query = request_data.get("query", "")
            force_tier = request_data.get("force_tier")

            if not query:
                await websocket.send_json({"error": "No query provided"})
                continue

            request = TAORequest(
                query=query,
                context=request_data.get("context", ""),
                force_tier=TierLevel(force_tier) if force_tier is not None else None,
            )

            # Create pipeline with WebSocket event callback
            async def send_event(event: PipelineEvent):
                try:
                    await websocket.send_json(event.model_dump())
                except Exception:
                    pass

            pipeline = TAOPipeline(event_callback=send_event)
            result = await pipeline.analyze(request)

            # Send final result
            await websocket.send_json({
                "event_type": "final_result",
                "data": result.model_dump(),
            })

    except WebSocketDisconnect:
        pass
