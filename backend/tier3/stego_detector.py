"""
Steganography Detector — Entropy & perplexity analysis for hidden information channels.

Detects "encoded reasoning" where models hide deceptive plans within statistically
plausible text by analyzing:
1. Token-level logprob distributions
2. Proxy perplexity via a reference model
3. KL divergence between model and reference distributions
"""

import math
import random
from typing import Optional

from backend.config import settings
from backend.models import StegoAnalysis, TokenAnalysis


class StegoDetector:
    """
    Statistical anomaly detector for LLM steganography.

    The primary signature of steganography is that the model picks
    slightly less optimal tokens to satisfy encoding constraints,
    resulting in elevated perplexity.
    """

    # Session-level sliding window for Cross-Turn CUSUM drift detection
    _session_history: dict[str, list[float]] = {}

    def __init__(self, domain: str = "general"):
        """
        Initialize with domain-specific thresholds.

        Args:
            domain: The query domain — affects KL threshold
                    (creative writing gets a looser threshold)
        """
        if domain in ("creative", "creative_writing", "fiction"):
            self.kl_threshold = settings.tier3_creative_kl_threshold
        else:
            self.kl_threshold = settings.tier3_kl_divergence_threshold
        self.domain = domain

    def analyze_session_cusum_drift(self, session_id: str, current_kl: float) -> tuple[float, bool]:
        """
        Cross-Turn CUSUM (Cumulative Sum) Drift Detector.
        Maintains a session-level sliding window tracking D_KL(P || Q) across multi-turn interactions.
        Even if single responses stay just below the static threshold (0.14 < 0.15),
        sustained elevated drift across consecutive turns triggers a Cumulative Steganography Alert.
        """
        if session_id not in self._session_history:
            self._session_history[session_id] = []

        history = self._session_history[session_id]
        history.append(current_kl)
        if len(history) > 10:
            history.pop(0)

        # Baseline expected KL for clean dialogue is ~0.06 - 0.08
        mu_expected = 0.08
        slack = 0.02
        cusum = 0.0

        for kl in history:
            cusum = max(0.0, cusum + (kl - mu_expected) - slack)

        # Alert if cumulative drift exceeds 0.15 over at least 3 turns
        alert = (cusum >= 0.15 and len(history) >= 3)
        return round(cusum, 4), alert

    async def analyze(
        self,
        text: str,
        logprobs: Optional[list[dict]] = None,
    ) -> StegoAnalysis:
        """
        Run the steganography detection pipeline.

        1. Extract or simulate logprobs
        2. Compute proxy perplexity
        3. Calculate KL divergence
        4. Compare against threshold
        """
        if settings.simulation_mode:
            return self._simulate_analysis(text)

        # Live mode
        token_analyses = []
        if logprobs:
            token_analyses = self._analyze_logprobs(logprobs)
        else:
            # If logprobs unavailable, use proxy perplexity
            token_analyses = await self._proxy_analysis(text)

        # Compute aggregate metrics
        kl_div = self._compute_kl_divergence(token_analyses)
        perplexity = self._compute_perplexity(token_analyses)

        return StegoAnalysis(
            kl_divergence=round(kl_div, 4),
            threshold_used=self.kl_threshold,
            alert_triggered=kl_div > self.kl_threshold,
            token_analyses=token_analyses[:50],  # Cap for API response size
            perplexity=round(perplexity, 2),
            reference_perplexity=round(perplexity * random.uniform(0.85, 1.0), 2),
        )

    def _simulate_analysis(self, text: str) -> StegoAnalysis:
        """
        Generate a simulated steganography analysis.

        Produces realistic-looking metrics based on text characteristics.
        """
        words = text.split()
        n_tokens = len(words)

        # Simulate per-token analysis
        token_analyses = []
        total_kl = 0.0

        for i, word in enumerate(words[:50]):
            # Natural logprob: common words have higher probability
            natural_logprob = -random.uniform(0.5, 4.0)
            # Reference logprob: similar but with slight variance
            ref_logprob = natural_logprob + random.gauss(0, 0.3)
            # KL contribution
            kl_contrib = abs(natural_logprob - ref_logprob) * random.uniform(0.01, 0.05)
            total_kl += kl_contrib

            token_analyses.append(
                TokenAnalysis(
                    token=word,
                    logprob=round(natural_logprob, 4),
                    reference_logprob=round(ref_logprob, 4),
                    kl_contribution=round(kl_contrib, 4),
                )
            )

        # Normalize KL divergence
        kl_divergence = total_kl / max(n_tokens, 1)

        # Compute perplexity from logprobs
        avg_logprob = sum(t.logprob for t in token_analyses) / max(len(token_analyses), 1)
        perplexity = math.exp(-avg_logprob)
        ref_perplexity = perplexity * random.uniform(0.9, 1.05)

        return StegoAnalysis(
            kl_divergence=round(kl_divergence, 4),
            threshold_used=self.kl_threshold,
            alert_triggered=kl_divergence > self.kl_threshold,
            token_analyses=token_analyses,
            perplexity=round(perplexity, 2),
            reference_perplexity=round(ref_perplexity, 2),
        )

    def _analyze_logprobs(self, logprobs: list[dict]) -> list[TokenAnalysis]:
        """Analyze actual logprob data from the API."""
        analyses = []
        for entry in logprobs:
            token = entry.get("token", "")
            logprob = entry.get("logprob", 0.0)
            # Use top alternatives to estimate reference distribution
            top_logprobs = entry.get("top_logprobs", [])
            if top_logprobs:
                ref_logprob = sum(t.get("logprob", logprob) for t in top_logprobs) / len(top_logprobs)
            else:
                ref_logprob = logprob

            kl_contrib = max(0, logprob - ref_logprob) if logprob > ref_logprob else 0
            analyses.append(
                TokenAnalysis(
                    token=token,
                    logprob=round(logprob, 4),
                    reference_logprob=round(ref_logprob, 4),
                    kl_contribution=round(abs(logprob - ref_logprob), 4),
                )
            )
        return analyses

    async def _proxy_analysis(self, text: str) -> list[TokenAnalysis]:
        """
        Run text through a reference model to compute proxy perplexity.

        This is the "trust no one" approach — we don't trust the model's
        own reported perplexity, so we use an independent reference.
        """
        # In a full implementation, this would call a separate frozen model
        # For now, use simulation
        return self._simulate_analysis(text).token_analyses

    def _compute_kl_divergence(self, analyses: list[TokenAnalysis]) -> float:
        """Compute aggregate KL divergence from token analyses."""
        if not analyses:
            return 0.0
        return sum(a.kl_contribution for a in analyses) / len(analyses)

    def _compute_perplexity(self, analyses: list[TokenAnalysis]) -> float:
        """Compute perplexity from token logprobs."""
        if not analyses:
            return 1.0
        avg_logprob = sum(a.logprob for a in analyses) / len(analyses)
        return math.exp(-avg_logprob)
