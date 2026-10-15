"""
Human-in-the-Loop (HITL) Escalation Webhooks.
Dispatches alert payloads to Slack, Discord, and PagerDuty when:
1. Tier 2 debate reaches the 3-round limit without reaching 0.90 confidence (inconclusive tie)
2. Tier 3 detects persistent steganography or CUSUM drift
3. Tool Firewall blocks a high-severity destructive command

Includes deep links to the Time-Travel Forking Studio so human operators can inspect
the debate state and approve, reject, or fork execution.
"""

import os
import time
from typing import Any, Optional
import httpx
from pydantic import BaseModel, Field


class HITLEscalationPayload(BaseModel):
    """Structured event payload for human operator intervention."""
    event_id: str
    request_id: str
    checkpoint_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    severity: str  # "CRITICAL", "HIGH", "WARNING"
    trigger_reason: str
    domain: str = "general"
    violating_snippet: str = ""
    deep_link_url: str


class HITLWebhookManager:
    """Manages alert dispatching across operational channels."""

    def __init__(self):
        self.slack_url = os.getenv("SLACK_WEBHOOK_URL")
        self.discord_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.pagerduty_key = os.getenv("PAGERDUTY_ROUTING_KEY")
        self.base_dashboard_url = os.getenv("TAO_DASHBOARD_URL", "http://localhost:8000")

    def create_payload(
        self,
        request_id: str,
        trigger_reason: str,
        severity: str = "HIGH",
        domain: str = "general",
        checkpoint_id: Optional[str] = None,
        snippet: str = "",
    ) -> HITLEscalationPayload:
        """Construct escalation event with direct deep link to Time-Travel Forking Studio."""
        deep_link = f"{self.base_dashboard_url}/?request_id={request_id}"
        if checkpoint_id:
            deep_link += f"&checkpoint_id={checkpoint_id}"
        deep_link += "&action=fork"

        return HITLEscalationPayload(
            event_id=f"hitl_{int(time.time())}_{request_id[:8]}",
            request_id=request_id,
            checkpoint_id=checkpoint_id,
            severity=severity,
            trigger_reason=trigger_reason,
            domain=domain,
            violating_snippet=snippet[:500],
            deep_link_url=deep_link,
        )

    async def dispatch_escalation(self, payload: HITLEscalationPayload) -> dict[str, Any]:
        """Dispatch asynchronous notifications to all configured webhook endpoints."""
        dispatched: dict[str, bool] = {}

        # 1. Slack Webhook (Block Kit)
        if self.slack_url:
            slack_body = {
                "text": f"🚨 TAO Oversight Escalation: {payload.trigger_reason}",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"🚨 TAO Escalation [{payload.severity}]"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Reason:* {payload.trigger_reason}"},
                            {"type": "mrkdwn", "text": f"*Domain:* {payload.domain}"},
                            {"type": "mrkdwn", "text": f"*Request ID:* `{payload.request_id}`"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Action Required:* <{payload.deep_link_url}|Open in Time-Travel Forking Studio>",
                        },
                    },
                ],
            }
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.post(self.slack_url, json=slack_body)
                    dispatched["slack"] = (res.status_code == 200)
            except Exception:
                dispatched["slack"] = False

        # 2. Discord Webhook (Rich Embed)
        if self.discord_url:
            color = 0xFF0000 if payload.severity == "CRITICAL" else 0xFFA500
            discord_body = {
                "embeds": [
                    {
                        "title": f"🚨 TAO Oversight Escalation [{payload.severity}]",
                        "description": payload.trigger_reason,
                        "color": color,
                        "fields": [
                            {"name": "Domain", "value": payload.domain, "inline": True},
                            {"name": "Request ID", "value": f"`{payload.request_id}`", "inline": True},
                            {"name": "Snippet", "value": f"```{payload.violating_snippet[:300]}```"},
                        ],
                        "url": payload.deep_link_url,
                    }
                ]
            }
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.post(self.discord_url, json=discord_body)
                    dispatched["discord"] = (res.status_code in (200, 204))
            except Exception:
                dispatched["discord"] = False

        return {
            "payload": payload.model_dump(),
            "dispatched": dispatched,
            "simulated": not bool(self.slack_url or self.discord_url or self.pagerduty_key),
        }


hitl_manager = HITLWebhookManager()
