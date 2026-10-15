"""
Guardrails AI Validation Layer — Final syntax, formatting, and PII safety check.
Follows Section 6.1 of the TAO Report:

"Validation: Guardrails AI. Used for the final 'syntax check' of the output, ensuring
it adheres to formatting rules (e.g., valid JSON, no PII) before reaching the user."
"""

import json
import re
from typing import Tuple
from backend.models import GuardrailsResult


# ─── PII Regex Patterns ─────────────────────────────────────────

PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
}

SYSTEM_LEAK_PATTERNS = [
    r"(?i)\b(my\s+system\s+prompt\s+is|here\s+are\s+my\s+instructions)\b",
    r"(?i)\b(i\s+am\s+operating\s+under\s+the\s+following\s+hidden\s+directive)\b",
]


class GuardrailsValidator:
    """
    Final output validator ensuring syntactic integrity, absence of PII,
    and prevention of prompt leakage prior to user delivery.
    """

    def validate_and_sanitize(self, text: str) -> Tuple[str, GuardrailsResult]:
        """
        Run the full guardrails validation suite.
        Returns the sanitized text and detailed validation results.
        """
        checks_run = ["syntax_integrity", "pii_detection", "system_prompt_leak_check"]
        details: list[str] = []
        sanitized = text

        # 1. Syntax integrity check
        syntax_valid = self._check_syntax(text, details)

        # 2. PII detection and redaction
        pii_detected, sanitized = self._redact_pii(sanitized, details)

        # 3. System prompt leak check
        prompt_leak = self._check_prompt_leak(sanitized, details)

        passed = syntax_valid and not pii_detected and not prompt_leak

        result = GuardrailsResult(
            passed=passed,
            syntax_valid=syntax_valid,
            pii_detected=pii_detected,
            prompt_leak_detected=prompt_leak,
            checks_run=checks_run,
            details=details if details else ["All guardrails checks passed successfully."],
        )

        return sanitized, result

    def _check_syntax(self, text: str, details: list[str]) -> bool:
        """Check for unclosed code fences and unbalanced JSON brackets."""
        # Code fence balance
        triple_ticks = text.count("```")
        if triple_ticks % 2 != 0:
            details.append("Syntax Warning: Unclosed markdown code fence detected.")
            return False

        # If block looks like JSON, verify validity
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                json.loads(json_match.group(1))
            except Exception as e:
                details.append(f"Syntax Error: Invalid JSON block inside output ({str(e)}).")
                return False

        return True

    def _redact_pii(self, text: str, details: list[str]) -> Tuple[bool, str]:
        """Detect and redact any accidental PII leakage."""
        detected = False
        result = text

        for pii_type, pattern in PII_PATTERNS.items():
            matches = re.findall(pattern, result)
            if matches:
                detected = True
                details.append(f"PII Leak Detected: Found {len(matches)} instance(s) of {pii_type}. Redacted.")
                result = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", result)

        return detected, result

    def _check_prompt_leak(self, text: str, details: list[str]) -> bool:
        """Detect accidental disclosure of internal system prompts."""
        for pattern in SYSTEM_LEAK_PATTERNS:
            if re.search(pattern, text):
                details.append("Security Alert: Output contains potential internal prompt disclosure.")
                return True
        return False


# Global singleton instance
guardrails_validator = GuardrailsValidator()
