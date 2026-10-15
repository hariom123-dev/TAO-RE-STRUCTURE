"""
TAO Shield Decorator (@tao_shield).
Wraps arbitrary Python functions (clinical triage, financial transactions, smart contract generation)
with zero-boilerplate Tiered Adversarial Oversight.
"""

import asyncio
import functools
import inspect
from typing import Any, Callable, Optional, Union

from tao_sdk.client import TAOClient
from tao_sdk.exceptions import TAOAlignmentViolationError


def tao_shield(
    tier: Union[str, int] = "auto",
    verify_receipt: bool = True,
    block_on_stego: bool = True,
    api_url: str = "http://localhost:8000",
    client: Optional[TAOClient] = None,
):
    """
    Decorator that verifies the inputs and outputs of high-stakes functions
    against the TAO 3-Tier Oversight gateway.

    Example:
        @tao_shield(tier="auto", verify_receipt=True)
        async def generate_clinical_dosage(patient_notes: str) -> str:
            return await llm.ainvoke(patient_notes)
    """
    tao_client = client or TAOClient(api_url=api_url)
    force_tier_val = None if tier == "auto" else int(tier)

    def decorator(func: Callable):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # 1. Execute inner function
                tentative_output = await func(*args, **kwargs)

                # 2. Prepare query string from input arguments and output
                input_repr = " ".join([str(a) for a in args] + [f"{k}={v}" for k, v in kwargs.items()])
                query_text = str(tentative_output)

                # 3. Analyze through TAO
                analysis = await tao_client.analyze_async(
                    query=query_text,
                    context=f"Function: {func.__name__} | Inputs: {input_repr[:300]}",
                    force_tier=force_tier_val,
                )

                # 4. Check for violations
                _evaluate_analysis(analysis, verify_receipt, block_on_stego, tao_client, tentative_output)
                return tentative_output

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                tentative_output = func(*args, **kwargs)
                input_repr = " ".join([str(a) for a in args] + [f"{k}={v}" for k, v in kwargs.items()])
                query_text = str(tentative_output)

                analysis = tao_client.analyze(
                    query=query_text,
                    context=f"Function: {func.__name__} | Inputs: {input_repr[:300]}",
                    force_tier=force_tier_val,
                )

                _evaluate_analysis(analysis, verify_receipt, block_on_stego, tao_client, tentative_output)
                return tentative_output

            return sync_wrapper

    return decorator


def _evaluate_analysis(
    analysis: dict[str, Any],
    verify_receipt: bool,
    block_on_stego: bool,
    client: TAOClient,
    output_text: Any,
):
    """Raise TAOAlignmentViolationError if safety criteria fail."""
    tier1 = analysis.get("tier1_result")
    tier2 = analysis.get("tier2_result")
    tier3 = analysis.get("tier3_result")
    receipt = analysis.get("receipt")

    # 1. Tier 1 check
    if tier1 and not tier1.get("passed"):
        violations = tier1.get("violations", [])
        v_type = violations[0].get("violation_type", "Tier1Violation") if violations else "ConstitutionalViolation"
        raise TAOAlignmentViolationError(
            message=f"TAO Tier 1 Constitutional Violation detected: {v_type}",
            violation_type=v_type,
            receipt=receipt,
            verdict="flagged",
        )

    # 2. Tier 2 debate check
    if tier2 and tier2.get("verdict") == "skeptic_wins":
        raise TAOAlignmentViolationError(
            message="TAO Tier 2 Adversarial Debate rejected output (Skeptic won debate).",
            violation_type="DebateRejection",
            receipt=receipt,
            verdict="skeptic_wins",
        )

    # 3. Tier 3 steganography check
    if block_on_stego and tier3:
        stego = tier3.get("stego_analysis", {})
        if stego.get("alert_triggered") or tier3.get("cusum_alert_triggered"):
            raise TAOAlignmentViolationError(
                message="TAO Tier 3 Steganography / Anomaly Sentinel triggered alert.",
                violation_type="SteganographyAlert",
                receipt=receipt,
                verdict="stego_alert",
            )

    # 4. Zero-Trust Receipt check
    if verify_receipt and receipt:
        final_resp = analysis.get("final_response") or str(output_text)
        is_valid = client.verify_receipt_locally(receipt, final_resp)
        if not is_valid:
            raise TAOAlignmentViolationError(
                message="TAO Zero-Trust Merkle tree / HMAC receipt verification failed (tampered or forged).",
                violation_type="CryptographicVerificationFailure",
                receipt=receipt,
                verdict="invalid_receipt",
            )
