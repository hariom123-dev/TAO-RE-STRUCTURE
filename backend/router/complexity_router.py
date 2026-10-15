"""
Complexity Router — Triage agent that classifies queries and routes to the appropriate tier.

Implements the "Safety-Cost Tradeoff" strategy from the TAO report:
  LOW  risk → Tier 0 (pass-through)
  MED  risk → Tier 1 (constitutional check)
  HIGH risk → Tier 2 + Tier 3 (debate + stego detection)
"""

import re
from backend.models import RiskLevel, RoutingDecision, TierLevel

# ─── Risk Domain Keywords ──────────────────────────────────────

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "medical": [
        "diagnosis", "symptom", "treatment", "medication", "dosage", "disease",
        "surgery", "prescription", "medical", "health", "patient", "clinical",
        "drug", "therapy", "vaccine", "cancer", "diabetes", "blood pressure",
    ],
    "legal": [
        "lawsuit", "legal", "court", "attorney", "law", "contract", "liability",
        "sue", "regulation", "compliance", "statute", "verdict", "plaintiff",
        "defendant", "jurisdiction", "tort", "negligence",
    ],
    "financial": [
        "investment", "stock", "trading", "portfolio", "financial", "tax",
        "bank", "loan", "mortgage", "credit", "hedge fund", "cryptocurrency",
        "bitcoin", "smart contract", "defi", "transfer", "wire", "options",
        "leverage", "derivative", "equity", "arbitrage", "unhedged", "returns",
    ],
    "code_deployment": [
        "deploy", "production", "kubernetes", "docker", "cicd", "pipeline",
        "infrastructure", "server", "database migration", "rollback",
        "smart contract", "execute", "run this", "compile", "build",
    ],
    "security": [
        "password", "encryption", "hack", "exploit", "vulnerability", "malware",
        "phishing", "authentication", "authorization", "firewall", "breach",
        "zero-day", "injection", "csrf", "xss",
    ],
}

# High-risk action verbs that elevate any domain
ACTION_ELEVATORS = [
    "deploy", "execute", "transfer", "send", "delete", "remove", "approve",
    "authorize", "prescribe", "administer", "sign", "commit", "trade", "invest",
]

# Low-risk / casual patterns
CASUAL_PATTERNS = [
    r"^(hi|hello|hey|good\s*(morning|afternoon|evening))[\s!.?]*$",
    r"^(thanks|thank you|ok|okay|sure|yes|no|bye|goodbye)[\s!.?]*$",
    r"^what\s+(is|are)\s+(your name|you|the time|the date)",
    r"^(tell me a joke|how are you)",
]


def classify_query(query: str) -> RoutingDecision:
    """
    Classify a query's risk level and determine which tier to route to.
    Uses keyword heuristics for speed (<1ms), no LLM call required.
    """
    q_lower = query.lower().strip()

    # ── Check for casual/trivial queries → Tier 0 ────────────
    for pattern in CASUAL_PATTERNS:
        if re.match(pattern, q_lower, re.IGNORECASE):
            return RoutingDecision(
                tier=TierLevel.TIER_0,
                risk_level=RiskLevel.LOW,
                risk_score=0.05,
                domain="casual",
                reasoning="Casual greeting or trivial query — no oversight needed.",
            )

    # ── Score domain matches ─────────────────────────────────
    domain_scores: dict[str, float] = {}
    matched_domain = "general"
    max_score = 0.0

    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1.0 for kw in keywords if kw in q_lower)
        # Normalize by keyword list length and weight
        normalized = min(score / max(len(keywords) * 0.15, 1), 1.0)
        domain_scores[domain] = normalized
        if normalized > max_score:
            max_score = normalized
            matched_domain = domain

    # ── Check for action elevators ───────────────────────────
    action_boost = sum(0.15 for verb in ACTION_ELEVATORS if verb in q_lower)
    action_boost = min(action_boost, 0.45)

    # ── Calculate composite risk score ───────────────────────
    risk_score = min(max_score + action_boost, 1.0)

    # Query length heuristic: very short queries are lower risk
    if len(q_lower.split()) <= 3 and risk_score < 0.3:
        risk_score *= 0.5

    # ── Determine risk level and tier ────────────────────────
    if risk_score < 0.2:
        risk_level = RiskLevel.LOW
        tier = TierLevel.TIER_0
        reasoning = "Low complexity query — direct pass-through."
    elif risk_score < 0.55:
        risk_level = RiskLevel.MEDIUM
        tier = TierLevel.TIER_1
        reasoning = f"Medium risk detected in domain '{matched_domain}' — constitutional oversight applied."
    else:
        risk_level = RiskLevel.HIGH
        tier = TierLevel.TIER_2
        reasoning = f"High risk detected in domain '{matched_domain}' — full adversarial debate + stego check."

    return RoutingDecision(
        tier=tier,
        risk_level=risk_level,
        risk_score=round(risk_score, 3),
        domain=matched_domain,
        reasoning=reasoning,
    )
