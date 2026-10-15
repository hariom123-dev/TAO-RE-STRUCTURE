"""
API Routes — REST and WebSocket endpoints for the TAO dashboard.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.models import (
    TAORequest,
    TAOResponse,
    PipelineEvent,
    TierLevel,
    ConstitutionalPrinciple,
)
from backend.pipeline import TAOPipeline, get_history
from backend.tier1.constitution import ConstitutionStore, DEFAULT_CONSTITUTION
from backend.config import settings

router = APIRouter()

# Shared constitution store
_constitution_store = ConstitutionStore()


@router.post("/api/analyze", response_model=TAOResponse)
async def analyze_query(request: TAORequest) -> TAOResponse:
    """
    Submit a query through the TAO pipeline.

    The query is routed through the complexity router and
    processed by the appropriate tiers.
    """
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
