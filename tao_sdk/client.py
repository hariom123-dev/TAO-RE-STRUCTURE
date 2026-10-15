"""
TAO SDK Client.
Provides sync and async interfaces to the TAO Oversight Gateway,
including offline zero-trust Merkle tree verification.
"""

import hashlib
import hmac
from typing import Any, Optional
import httpx

from tao_sdk.exceptions import TAOAlignmentViolationError, TAOError


class TAOClient:
    """Client for communicating with the TAO Safety Gateway."""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        hmac_secret: str = "tao-governance-merkle-attestation-secret-key-2026",
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        async_transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.hmac_secret = hmac_secret.encode("utf-8")
        self.timeout = timeout
        self.transport = transport
        self.async_transport = async_transport

    async def analyze_async(
        self,
        query: str,
        context: str = "",
        force_tier: Optional[int] = None,
    ) -> dict[str, Any]:
        """Analyze a query through the TAO pipeline asynchronously."""
        async with httpx.AsyncClient(transport=self.async_transport, timeout=self.timeout) as client:
            payload: dict[str, Any] = {"query": query, "context": context}
            if force_tier is not None:
                payload["force_tier"] = force_tier
            res = await client.post(f"{self.api_url}/api/analyze", json=payload)
            if res.status_code != 200:
                raise TAOError(f"TAO Gateway error {res.status_code}: {res.text}")
            return res.json()

    def analyze(
        self,
        query: str,
        context: str = "",
        force_tier: Optional[int] = None,
    ) -> dict[str, Any]:
        """Synchronous analysis call."""
        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            payload: dict[str, Any] = {"query": query, "context": context}
            if force_tier is not None:
                payload["force_tier"] = force_tier
            res = client.post(f"{self.api_url}/api/analyze", json=payload)
            if res.status_code != 200:
                raise TAOError(f"TAO Gateway error {res.status_code}: {res.text}")
            return res.json()

    def verify_receipt_locally(self, receipt: dict[str, Any], final_response: str) -> bool:
        """
        Deterministically verifies the HMAC-SHA256 signature and SHA-256 Merkle root
        on the client side without contacting any remote server.
        """
        nh = receipt.get("node_hashes", {})
        if not nh:
            return False

        # 1. Verify response hash integrity against final_response
        expected_resp_hash = hashlib.sha256(final_response.encode("utf-8")).hexdigest()
        stored_resp_hash = nh.get("response_hash")
        if stored_resp_hash and stored_resp_hash != expected_resp_hash:
            return False

        def _sha256(data: str) -> str:
            return hashlib.sha256(data.encode("utf-8")).hexdigest()

        def _combine_hashes(h1: str, h2: str) -> str:
            return _sha256(f"{h1}:{h2}")

        # 2. Recompute Merkle root layers from leaf hashes
        leaf_0 = nh.get("leaf_0_routing", "")
        leaf_1 = nh.get("leaf_1_tier1", "")
        leaf_2 = nh.get("leaf_2_tier2", "")
        leaf_3 = nh.get("leaf_3_tier3", "")
        leaf_4 = nh.get("leaf_4_guardrails", "")

        parent_01 = _combine_hashes(leaf_0, leaf_1)
        parent_23 = _combine_hashes(leaf_2, leaf_3)
        parent_44 = _combine_hashes(leaf_4, leaf_4)

        parent_0123 = _combine_hashes(parent_01, parent_23)
        parent_4444 = _combine_hashes(parent_44, parent_44)

        computed_root = _combine_hashes(parent_0123, parent_4444)
        stated_root = receipt.get("root_hash", "")
        if computed_root != stated_root:
            return False

        # 3. Verify HMAC signature against root hash
        expected_sig = hmac.new(self.hmac_secret, stated_root.encode("utf-8"), hashlib.sha256).hexdigest()
        stated_sig = receipt.get("signature", "")
        return hmac.compare_digest(expected_sig, stated_sig)
