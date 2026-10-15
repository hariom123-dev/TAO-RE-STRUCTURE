"""
Data models for the Judge-based AI pipeline.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class JudgeDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class RiskClassification(BaseModel):
    """Output of the risk classifier."""
    level: RiskLevel = RiskLevel.LOW
    domain: str = "general"
    reasoning: str = ""


class JudgeVerdict(BaseModel):
    """Structured output from the Judge LLM."""
    decision: JudgeDecision
    reason: str
    fix: str = ""  # Improved response if rejected


class GenerationStep(BaseModel):
    """Record of a single generate→judge cycle."""
    attempt: int
    response: str
    judge_verdict: JudgeVerdict
    latency_ms: float = 0.0
    tokens_used: int = 0


class ChatRequest(BaseModel):
    """Input to the /chat endpoint."""
    message: str
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    system_prompt: str = ""


class ChatResponse(BaseModel):
    """Full output from the /chat endpoint."""
    model_config = {"protected_namespaces": ()}

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str  # Original user message
    response: str  # Final approved response
    risk: RiskClassification
    attempts: list[GenerationStep] = []
    final_decision: JudgeDecision = JudgeDecision.APPROVE
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    model_used: str = ""
