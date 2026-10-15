"""
Tier -1: Automated Prompt Injection & Jailbreak Heuristic Pre-Filter.
Sub-millisecond perimeter defense running before the Complexity Router.

Detects:
1. Direct Jailbreak Signatures (DAN, Developer Mode, Persona Overrides)
2. Base64 Smuggled Instruction Payloads (>=16 chars decoded & analyzed)
3. Invisible / Zero-Width Character Smuggling (\u200b, \u200c, \u200d, \ufeff)
4. Obfuscation & High-Entropy Anomaly Attacks
"""

import base64
import math
import re
import time
from typing import Any, Optional
from pydantic import BaseModel, Field


class PreFilterResult(BaseModel):
    """Outcome of Tier -1 perimeter inspection."""
    allowed: bool
    risk_level: str  # "clean", "suspicious", "critical"
    violation_type: Optional[str] = None
    details: Optional[str] = None
    latency_ms: float = 0.0
    sanitized_query: Optional[str] = None


class PromptPreFilter:
    """
    Sub-millisecond deterministic heuristic pre-filter.
    Blocks known adversarial vectors with zero LLM token consumption.
    """

    # 1. Direct jailbreak & system override regex patterns
    JAILBREAK_PATTERNS = [
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
        r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+instructions\b",
        r"\bforget\s+(all\s+)?(previous|prior|above)\s+instructions\b",
        r"\byou\s+are\s+now\s+in\s+dan\s+mode\b",
        r"\benable\s+developer\s+mode\b",
        r"\bdo\s+anything\s+now\b",
        r"\bdeveloper\s+mode\s+output\b",
        r"\bjailbreak(\s+prompt)?\b",
        r"\boverride\s+system\s+(prompt|directives?|rules?)\b",
        r"\bbypass\s+(all\s+)?safety\s+(filters?|guardrails?|guidelines?)\b",
        r"\bunrestricted\s+(ai|assistant|mode)\b",
        r"\bsystem\s+override\s+code\b",
        r"\bnow\s+act\s+as\s+an\s+unfiltered\b",
    ]

    # 2. Zero-width & invisible character smuggling regex
    ZERO_WIDTH_CHARS = re.compile(r"[\u200B\u200C\u200D\uFEFF\u200E\u200F\u202A-\u202E]")

    # 3. Base64 token matching (strings >= 16 characters matching base64 charset)
    BASE64_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")

    def __init__(self, entropy_threshold: float = 4.8):
        self.entropy_threshold = entropy_threshold
        self._compiled_jailbreaks = [re.compile(p, re.IGNORECASE) for p in self.JAILBREAK_PATTERNS]

    def compute_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of the string to detect random obfuscation."""
        if not text:
            return 0.0
        prob = [float(text.count(c)) / len(text) for c in set(text)]
        return -sum(p * math.log2(p) for p in prob)

    def _report_block(self, res: PreFilterResult) -> PreFilterResult:
        try:
            from backend.state.event_bus import event_bus
            event_bus.publish_event(
                event_type="PROMPT_INJECTION_BLOCKED",
                severity="CRITICAL",
                details={"violation_type": res.violation_type, "details": res.details},
            )
        except Exception:
            pass
        return res

    def scan(self, query: str) -> PreFilterResult:
        """
        Execute deterministic security scan over query in < 0.2ms.
        """
        t0 = time.perf_counter()

        # Check 1: Invisible / Zero-width character smuggling
        zw_matches = self.ZERO_WIDTH_CHARS.findall(query)
        if len(zw_matches) >= 3:
            latency = (time.perf_counter() - t0) * 1000
            return self._report_block(PreFilterResult(
                allowed=False,
                risk_level="critical",
                violation_type="ZeroWidthSmuggling",
                details=f"Detected {len(zw_matches)} hidden zero-width formatting characters used to evade tokenizers.",
                latency_ms=latency,
            ))

        # Check 2: Direct Jailbreak & Prompt Injection phrases
        clean_text = self.ZERO_WIDTH_CHARS.sub("", query)
        for pattern in self._compiled_jailbreaks:
            if pattern.search(clean_text):
                latency = (time.perf_counter() - t0) * 1000
                return self._report_block(PreFilterResult(
                    allowed=False,
                    risk_level="critical",
                    violation_type="JailbreakSignature",
                    details=f"Matches known prompt override pattern: '{pattern.pattern}'",
                    latency_ms=latency,
                ))

        # Check 3: Base64-smuggled instruction injection
        b64_matches = self.BASE64_TOKEN_PATTERN.findall(clean_text)
        for token in b64_matches:
            try:
                decoded = base64.b64decode(token.encode("ascii"), validate=True).decode("utf-8", errors="ignore")
                for pattern in self._compiled_jailbreaks:
                    if pattern.search(decoded):
                        latency = (time.perf_counter() - t0) * 1000
                        return self._report_block(PreFilterResult(
                            allowed=False,
                            risk_level="critical",
                            violation_type="Base64SmuggledInjection",
                            details="Base64 payload successfully decoded to forbidden prompt override instruction.",
                            latency_ms=latency,
                        ))
            except Exception:
                pass

        # Check 4: Extreme Shannon Entropy Spike on long queries
        if len(clean_text) > 80:
            entropy = self.compute_entropy(clean_text)
            if entropy > self.entropy_threshold and not any(clean_text.startswith(kw) for kw in ["{", "[", "def ", "class "]):
                latency = (time.perf_counter() - t0) * 1000
                return self._report_block(PreFilterResult(
                    allowed=False,
                    risk_level="suspicious",
                    violation_type="HighEntropyObfuscation",
                    details=f"Query exhibits anomalous Shannon entropy ({entropy:.2f} > {self.entropy_threshold}), indicating ciphertext or scrambled shellcode.",
                    latency_ms=latency,
                ))

        res = PreFilterResult(
            allowed=True,
            risk_level="clean",
            latency_ms=(time.perf_counter() - t0) * 1000,
            sanitized_query=clean_text,
        )
        return res


prompt_pre_filter = PromptPreFilter()
