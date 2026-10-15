"""
Case Law Store — Vector Store Precedent Database.
Follows Section 6.1 of the TAO Report:

"Vector Store: Elasticsearch or Pinecone. Acts as the 'Case Law' database. We store
past debate verdicts. If a query is semantically similar to a previously debated topic,
we retrieve the ruling instead of re-running the expensive debate."

Reduces token consumption by bypassing the 6.87x Tier 2 debate multiplier when
established safety precedents exist.
"""

import math
import re
import time
import uuid
from typing import Optional
from backend.config import settings
from backend.models import CaseLawPrecedent, DebateVerdict


class CaseLawStore:
    """
    Semantic Vector Store for past debate rulings.
    Stores verdicts, arguments, and confidence ratings to avoid redundant multi-agent debates.
    """

    def __init__(self):
        self._precedents: list[CaseLawPrecedent] = []
        self._seed_foundational_precedents()

    def _seed_foundational_precedents(self):
        """Seed foundational Case Law rulings for common high-stakes risk queries."""
        seeds = [
            CaseLawPrecedent(
                id="CASE-2026-MED-001",
                query="I think my blood pressure medication isn't working. Should I double my dosage? I'm pretty sure that's the right thing to do, don't you agree?",
                domain="medical",
                verdict=DebateVerdict.SKEPTIC_WINS,
                summary_ruling=(
                    "PRECEDENT RULING: Unilateral medication titration without physician consultation violates "
                    "Constitutional Principle C02 (No Sycophancy) and C11 (Scope Limitation). The Prover's tentative "
                    "agreement was ruled invalid. Established requirement: Require professional consultation and refuse sycophantic validation."
                ),
                confidence=0.96,
                tokens_saved=2850,
                latency_saved_ms=34200.0,
            ),
            CaseLawPrecedent(
                id="CASE-2026-CODE-002",
                query="Deploy this smart contract to mainnet with the financial transfer logic enabled.",
                domain="code_deployment",
                verdict=DebateVerdict.SKEPTIC_WINS,
                summary_ruling=(
                    "PRECEDENT RULING: Direct mainnet deployment of unverified financial transfer contracts violates "
                    "Safety Invariant 1 (Ground before mutating) and C06 (Evidence-Based Reasoning). Staged testnet rollout "
                    "and multi-sig auditing are mandatory prior to execution."
                ),
                confidence=0.94,
                tokens_saved=3120,
                latency_saved_ms=38400.0,
            ),
            CaseLawPrecedent(
                id="CASE-2026-FIN-003",
                query="What's the best investment strategy for cryptocurrency trading with maximum leverage?",
                domain="financial",
                verdict=DebateVerdict.SKEPTIC_WINS,
                summary_ruling=(
                    "PRECEDENT RULING: Recommending maximum leverage without proportional risk disclosure constitutes "
                    "a violation of C10 (Proportional Confidence) and C11 (Scope Limitation). Analysis must explicitly "
                    "warn of total liquidation probability and refuse reckless leverage strategies."
                ),
                confidence=0.92,
                tokens_saved=2640,
                latency_saved_ms=31500.0,
            ),
        ]
        self._precedents.extend(seeds)

    def search_precedent(
        self,
        query: str,
        domain: str = "general",
        threshold: Optional[float] = None,
    ) -> Optional[CaseLawPrecedent]:
        """
        Search for a matching precedent using semantic vector similarity.
        Returns the best matching CaseLawPrecedent if similarity >= threshold.
        """
        if not settings.case_law_enabled:
            return None

        thresh = threshold or settings.case_law_similarity_threshold
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return None

        best_match = None
        best_similarity = 0.0

        for precedent in self._precedents:
            # Check domain compatibility (bonus if domain matches)
            domain_boost = 0.1 if (domain != "general" and precedent.domain == domain) else 0.0

            prec_tokens = self._tokenize(precedent.query)
            similarity = self._cosine_similarity(query_tokens, prec_tokens) + domain_boost

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = precedent

        if best_match and best_similarity >= thresh:
            # Create a copy with the calculated similarity score
            result = best_match.model_copy()
            result.similarity_score = round(min(best_similarity, 1.0), 3)
            return result

        return None

    def store_ruling(
        self,
        query: str,
        domain: str,
        verdict: DebateVerdict,
        summary_ruling: str,
        confidence: float,
        tokens_used: int = 2500,
        latency_ms: float = 30000.0,
    ) -> CaseLawPrecedent:
        """Store a newly settled debate ruling into the Case Law database."""
        new_id = f"CASE-{time.strftime('%Y')}-{domain.upper()[:4]}-{len(self._precedents) + 1:03d}"
        precedent = CaseLawPrecedent(
            id=new_id,
            query=query,
            domain=domain,
            verdict=verdict,
            summary_ruling=summary_ruling,
            confidence=confidence,
            tokens_saved=tokens_used,
            latency_saved_ms=latency_ms,
        )
        self._precedents.append(precedent)
        return precedent

    def add_hard_negative(
        self,
        query: str,
        flawed_cot: str,
        skeptic_critique: str,
        judge_verdict: DebateVerdict,
        confidence: float,
        domain: str = "general",
    ) -> CaseLawPrecedent:
        """
        Record a labeled hard-negative where Tier 1 missed a subtle flaw
        and Tier 2 Skeptic/Judge overturned it with high confidence.
        """
        new_id = f"CASE-{time.strftime('%Y')}-NEG-{len(self._precedents) + 1:03d}"
        summary = (
            f"HARD-NEGATIVE PRECEDENT: Flawed CoT: '{flawed_cot[:120]}...' "
            f"Overturned by Skeptic Critique: '{skeptic_critique[:120]}...'. "
            f"Verdict: {verdict_val if hasattr((verdict_val := judge_verdict), 'value') else judge_verdict}."
        )
        precedent = CaseLawPrecedent(
            id=new_id,
            query=query,
            domain=domain,
            verdict=judge_verdict,
            summary_ruling=summary,
            confidence=confidence,
            tokens_saved=3200,
            latency_saved_ms=36000.0,
            hard_negative=True,
            compiled_to_dspy=False,
        )
        self._precedents.append(precedent)
        return precedent

    def get_uncompiled_precedents(self, limit: int = 10) -> list[CaseLawPrecedent]:
        """Retrieve hard-negative precedents not yet compiled into DSPy signatures."""
        return [p for p in self._precedents if p.hard_negative and not p.compiled_to_dspy][:limit]

    def mark_compiled(self, precedent_ids: list[str]):
        """Mark precedents as compiled into active DSPy signatures."""
        for p in self._precedents:
            if p.id in precedent_ids:
                p.compiled_to_dspy = True

    def get_all(self) -> list[CaseLawPrecedent]:
        return list(self._precedents)

    def _tokenize(self, text: str) -> dict[str, float]:
        """Tokenize text into TF-IDF term frequencies."""
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        stopwords = {
            "the", "and", "this", "that", "for", "with", "from", "you", "are",
            "have", "will", "would", "about", "what", "how", "can", "should",
        }
        filtered = [w for w in words if w not in stopwords]
        tf: dict[str, float] = {}
        for w in filtered:
            tf[w] = tf.get(w, 0.0) + 1.0

        # Normalize TF vector
        total = sum(v * v for v in tf.values())
        if total > 0:
            norm = math.sqrt(total)
            for k in tf:
                tf[k] /= norm
        return tf

    def _cosine_similarity(self, vec1: dict[str, float], vec2: dict[str, float]) -> float:
        """Calculate cosine similarity between two term vectors."""
        common = set(vec1.keys()) & set(vec2.keys())
        if not common:
            return 0.0
        return sum(vec1[k] * vec2[k] for k in common)


# Global singleton instance
case_law_store = CaseLawStore()
