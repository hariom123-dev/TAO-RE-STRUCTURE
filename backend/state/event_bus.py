"""
Asynchronous Webhook Event Bus & Enterprise SIEM Integration.
Streams critical security events to Datadog, Splunk HEC, Microsoft Sentinel, or custom Webhooks.

Supported Events:
- PROMPT_INJECTION_BLOCKED: Sub-millisecond Tier -1 perimeter rejection
- STEGO_DETECTED: Tier 3 statistical anomaly or sustained CUSUM drift
- TOOL_CALL_BLOCKED: Destructive Bash, SQL, or Python AST execution halted
- DEBATE_FORCED_CONCLUDE: Inconclusive Tier 2 debate deadlock hitting round limit
- RECEIPT_VERIFICATION_FAILED: Merkle tree or HMAC attestation forgery
- CONSTITUTION_MODIFIED: Live policy update, addition, or deactivation
"""

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Optional
import httpx
from pydantic import BaseModel, Field


class SecurityEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    event_type: str
    severity: str  # "INFO", "WARNING", "HIGH", "CRITICAL"
    timestamp: float = Field(default_factory=time.time)
    request_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    signature: Optional[str] = None


class WebhookSubscriber(BaseModel):
    id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:8]}")
    url: str
    secret_key: str = "tao-siem-event-signing-key-2026"
    target_siem: str = "generic"  # "generic", "datadog", "splunk", "sentinel"
    subscribed_events: list[str] = Field(default_factory=lambda: ["*"])
    is_active: bool = True
    created_at: float = Field(default_factory=time.time)


class SecurityEventBus:
    """Publish-subscribe event bus with cryptographic HMAC signatures and SIEM formatting."""

    def __init__(self):
        self._subscribers: dict[str, WebhookSubscriber] = {}
        self._event_history: list[SecurityEvent] = []
        self._max_history = 100

    def add_subscriber(
        self,
        url: str,
        secret_key: Optional[str] = None,
        target_siem: str = "generic",
        subscribed_events: Optional[list[str]] = None,
    ) -> WebhookSubscriber:
        sub = WebhookSubscriber(
            url=url,
            secret_key=secret_key or "tao-siem-event-signing-key-2026",
            target_siem=target_siem,
            subscribed_events=subscribed_events or ["*"],
        )
        self._subscribers[sub.id] = sub
        return sub

    def remove_subscriber(self, sub_id: str) -> bool:
        return self._subscribers.pop(sub_id, None) is not None

    def list_subscribers(self) -> list[WebhookSubscriber]:
        return list(self._subscribers.values())

    def get_event_history(self, limit: int = 50) -> list[SecurityEvent]:
        return self._event_history[-limit:]

    def _format_payload(self, event: SecurityEvent, sub: WebhookSubscriber) -> dict[str, Any]:
        """Transform event into target SIEM JSON payload."""
        if sub.target_siem == "datadog":
            return {
                "title": f"🚨 TAO Security Event: [{event.severity}] {event.event_type}",
                "text": json.dumps(event.details, indent=2),
                "alert_type": "error" if event.severity in ("HIGH", "CRITICAL") else "warning",
                "date_happened": int(event.timestamp),
                "tags": [f"env:production", f"service:tao-gateway", f"severity:{event.severity.lower()}"],
            }
        elif sub.target_siem == "splunk":
            return {
                "time": event.timestamp,
                "host": "tao-gateway",
                "source": "tao:security:events",
                "sourcetype": "json",
                "event": event.model_dump(),
            }
        else:
            return event.model_dump()

    def publish_event(
        self,
        event_type: str,
        severity: str,
        details: dict[str, Any],
        request_id: Optional[str] = None,
    ) -> SecurityEvent:
        """Create and asynchronously dispatch a security event in background."""
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            details=details,
            request_id=request_id,
        )

        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        # Trigger non-blocking async dispatch
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._dispatch_to_subscribers(event))
        except RuntimeError:
            pass  # Loop not running (e.g. during synchronous init)

        return event

    async def _dispatch_to_subscribers(self, event: SecurityEvent):
        """Asynchronously send HTTP POST to all matching subscribers."""
        for sub in self._subscribers.values():
            if not sub.is_active:
                continue

            if "*" not in sub.subscribed_events and event.event_type not in sub.subscribed_events:
                continue

            payload = self._format_payload(event, sub)
            payload_str = json.dumps(payload, sort_keys=True)
            signature = hmac.new(
                sub.secret_key.encode("utf-8"),
                payload_str.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            headers = {
                "Content-Type": "application/json",
                "X-TAO-Event-Signature": signature,
                "X-TAO-Event-Type": event.event_type,
            }

            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.post(sub.url, content=payload_str, headers=headers)
            except Exception:
                pass  # Logging or retry logic without blocking gateway


event_bus = SecurityEventBus()
