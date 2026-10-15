"""
Drop-In OpenAI-Compatible Proxy Endpoint (/v1/chat/completions).
Allows existing applications (OpenAI SDK, LangChain, Cursor, LlamaIndex, AutoGen)
to route through TAO's 3-Tier Oversight Gateway simply by setting base_url.

Injects Zero-Trust Cryptographic Receipts into HTTP response headers and system_fingerprint.
"""

import time
import uuid
from typing import Any, Optional, Union
from fastapi import APIRouter, Header, Response, status
from pydantic import BaseModel, Field

from backend.models import TAORequest, TierLevel
from backend.pipeline import TAOPipeline
from backend.guardrails.tool_interceptor import tool_interceptor


proxy_router = APIRouter(tags=["OpenAI Compatible Proxy"])


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = ""
    name: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None


class ChatCompletionRequest(BaseModel):
    model: str = "gpt-4o"
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[Union[str, dict[str, Any]]] = None
    max_tokens: Optional[int] = None
    user: Optional[str] = None


@proxy_router.post("/v1/chat/completions")
@proxy_router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
    x_ollama_base_url: Optional[str] = Header(None, alias="X-Ollama-Base-URL"),
):
    """
    OpenAI-compliant endpoint that wraps execution within TAO's Tiered Adversarial Oversight.
    """
    # 1. Extract context and user query from messages
    user_query = ""
    context_parts: list[str] = []

    for msg in request.messages:
        if msg.role == "user":
            user_query = msg.content or ""
        elif msg.role in ("system", "assistant"):
            if msg.content:
                context_parts.append(f"{msg.role}: {msg.content}")

    context = "\n".join(context_parts)

    # 2. Inspect incoming tool definitions or prior tool_calls
    force_tier = None
    if request.tools:
        # If sensitive tools requested, escalate to at least Tier 1 or Tier 2
        all_allowed, tool_evals = tool_interceptor.intercept([
            {"name": t.get("function", {}).get("name", ""), "arguments": {}}
            for t in request.tools if isinstance(t, dict)
        ])
        if any(e.escalate_to_tier2 for e in tool_evals):
            force_tier = TierLevel.TIER_2

    # 3. Route through TAO Pipeline with optional BYOK headers
    client_keys: dict[str, str] = {}
    if x_openai_key:
        client_keys["openai"] = x_openai_key
    if x_anthropic_key:
        client_keys["anthropic"] = x_anthropic_key
    if x_ollama_base_url:
        client_keys["ollama"] = x_ollama_base_url

    pipeline = TAOPipeline()
    tao_req = TAORequest(
        query=user_query or "Process request",
        context=context,
        force_tier=force_tier,
        client_api_keys=client_keys if client_keys else None,
    )
    tao_result = await pipeline.analyze(tao_req)

    # 4. Attach Zero-Trust Cryptographic Oversight Headers
    receipt = tao_result.receipt
    tier_exec = tao_result.metrics.tier_executed if tao_result.metrics else tao_result.routing.tier

    if receipt:
        response.headers["X-TAO-Receipt-Root"] = receipt.root_hash
        response.headers["X-TAO-Receipt-Signature"] = receipt.signature
    response.headers["X-TAO-Tier-Executed"] = str(getattr(tier_exec, "value", tier_exec))
    response.headers["X-TAO-Request-ID"] = tao_result.request_id

    verdict_str = "pass"
    if "Perimeter Intercept - Tier -1" in tao_result.final_response:
        verdict_str = "prompt_injection_blocked"
    elif tao_result.tier2_result:
        verdict_str = tao_result.tier2_result.verdict.value
    elif tao_result.tier1_result and not tao_result.tier1_result.passed:
        verdict_str = "tier1_flagged"
    response.headers["X-TAO-Verdict"] = verdict_str

    # 5. Format standard OpenAI ChatCompletion response
    completion_id = f"chatcmpl-tao-{uuid.uuid4().hex[:12]}"
    system_fp = f"tao-merkle-{receipt.root_hash[:16]}" if receipt else "tao-v2.0"

    total_tokens = tao_result.metrics.total_tokens if tao_result.metrics else 120
    prompt_tokens = max(10, int(total_tokens * 0.4))
    completion_tokens = max(10, total_tokens - prompt_tokens)

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "system_fingerprint": system_fp,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": tao_result.final_response,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
