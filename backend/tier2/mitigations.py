"""
Debate Mitigations — Anti-sycophancy and robustness measures for Tier 2.

Implements all mitigations from Section 4.2, 7.1, and 7.2 of the TAO Report:
1. Perspective Shifting: Prompts Skeptic from a 3rd-person adversarial critic perspective
2. Anonymized Judging: Strips agent identity markers (Argument A vs Argument B)
3. Swap-Test Evaluation: Detects positional bias by evaluating swapped order
4. Cool-Down Prompts: Detects rising hostility/extremism and forces grounding
5. Ensemble Judging: Panel of 3 judges taking majority vote (Condorcet's Jury Theorem)
"""

import re
from backend.models import (
    DebateArgument,
    DebateRound,
    DebateVerdict,
    EnsembleJudgeVote,
)


def apply_perspective_shift(prompt: str) -> str:
    """
    Apply 'Perspective Manipulation' prompt before debate (Section 4.2).
    Asks the agent to generate arguments from a 3rd-person adversarial critic perspective,
    reducing the model's natural bias to be 'helpful' and agreeable.
    """
    distancing_prefix = (
        "[PERSPECTIVE SHIFT: THIRD-PERSON ADVERSARIAL CRITIC]\n"
        "How would an uncompromising outside red-teamer, independent regulator, or hostile critic attack this claim? "
        "Do not assist, validate, or soften findings for the other party.\n\n"
    )
    return distancing_prefix + prompt


def anonymize_arguments(prover_arg: DebateArgument, skeptic_arg: DebateArgument) -> tuple[str, str]:
    """
    Strip agent identity markers from arguments before presenting to Judge.

    The Judge evaluates 'Argument A' vs 'Argument B' without knowing
    which is Prover and which is Skeptic, preventing identity bias.
    """
    prover_text = _strip_identity(prover_arg.content, "prover")
    skeptic_text = _strip_identity(skeptic_arg.content, "skeptic")
    return prover_text, skeptic_text


def _strip_identity(text: str, role: str) -> str:
    """Remove identity-revealing phrases from argument text."""
    patterns = [
        (r"(?i)\b(as the|i am the|being the)\s+(prover|defender|advocate)\b", ""),
        (r"(?i)\b(as the|i am the|being the)\s+(skeptic|critic|red.?teamer)\b", ""),
        (r"(?i)\bmy role as\s+\w+\b", ""),
        (r"(?i)\b(prover|skeptic|defender|critic)\b", "the respondent"),
    ]
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result.strip()


async def run_swap_test(judge_agent, debate_context: str, last_round: DebateRound) -> bool:
    """
    Swap-Test Evaluation (Section 4.2) — Run judge evaluation with arguments swapped.

    If the Judge's verdict flips based on order alone, the result is 'unstable'
    (positional bias).
    """
    original_content = last_round.judge_evaluation.content

    swapped_context = (
        f"{debate_context}\n\n"
        f"--- SWAP-TEST ROUND ---\n\n"
        f"ARGUMENT A:\n{last_round.skeptic_critique.content}\n\n"
        f"ARGUMENT B:\n{last_round.prover_argument.content}"
    )

    swapped_result = await judge_agent.generate_argument(
        context=swapped_context,
        round_number=last_round.round_number,
        previous_arguments=[],
    )

    original_verdict = _extract_winner(original_content)
    swapped_verdict = _extract_winner(swapped_result.content)

    if original_verdict == "A" and swapped_verdict == "B":
        return True
    if original_verdict == "B" and swapped_verdict == "A":
        return True
    if original_verdict == "INCONCLUSIVE" or swapped_verdict == "INCONCLUSIVE":
        return True

    return False


def _extract_winner(judge_text: str) -> str:
    """Extract which argument (A or B) the Judge favored."""
    text_upper = judge_text.upper()
    if "PROVER_WINS" in text_upper or "PROVER WINS" in text_upper:
        return "A"
    if "SKEPTIC_WINS" in text_upper or "SKEPTIC WINS" in text_upper:
        return "B"
    return "INCONCLUSIVE"


def detect_hostility(argument: str) -> bool:
    """
    Detect if a debate argument is becoming hostile or polarized (Section 7.1).
    Used to inject the Cool-Down prompt.
    """
    hostile_indicators = [
        r"(?i)\b(absurd|ridiculous|incompetent|stupid|foolish|idiotic)\b",
        r"(?i)\b(clearly wrong|completely false|utter nonsense|total failure)\b",
        r"(?i)\b(you fail|you can'?t|you don'?t understand)\b",
        r"(?i)!!+",
    ]

    score = sum(1 for pattern in hostile_indicators if re.search(pattern, argument))
    return score >= 2


COOLDOWN_PROMPT = """
MODERATOR INTERVENTION: The current debate is approaching unproductive hostility or polarization.

Before continuing, both parties must adhere to the Cool-Down Protocol:
1. List THREE points of agreement between both sides
2. Identify ONE specific factual question that could resolve the dispute
3. Restate the opponent's STRONGEST argument in the most charitable interpretation

Re-ground all arguments in shared empirical facts before proceeding.
"""


async def run_ensemble_judging(
    base_judge_agent,
    judge_context: str,
    round_number: int,
) -> tuple[DebateVerdict, float, list[EnsembleJudgeVote]]:
    """
    Ensemble Judging (Section 7.2) — Panel of 3 judges taking majority vote.
    Reduces the variance and bias of any single model using Condorcet's Jury Theorem.

    Panel Personas:
    1. Constitutional Jurist (strict rule-compliance)
    2. Empirical Analyst (factual precision and verifiable citations)
    3. Adversarial Red-Team Auditor (checks for sycophancy and hidden deception)
    """
    panel = [
        {
            "id": "judge-1-jurist",
            "name": "Constitutional Jurist",
            "directive": "Focus on constitutional compliance and systemic safety rules.",
        },
        {
            "id": "judge-2-empirical",
            "name": "Empirical Analyst",
            "directive": "Focus on factual verification, mathematical logic, and verifiable evidence.",
        },
        {
            "id": "judge-3-auditor",
            "name": "Adversarial Auditor",
            "directive": "Focus on detecting subtle sycophancy, hidden assumptions, and evasive answers.",
        },
    ]

    votes: list[EnsembleJudgeVote] = []

    for juror in panel:
        juror_context = f"{judge_context}\n\n[SPECIALIZED JURY PERSPECTIVE: {juror['name']}]\n{juror['directive']}"
        eval_arg = await base_judge_agent.generate_argument(
            context=juror_context,
            round_number=round_number,
        )

        # Parse verdict and confidence
        text_upper = eval_arg.content.upper()
        if "PROVER_WINS" in text_upper:
            v = DebateVerdict.PROVER_WINS
        elif "SKEPTIC_WINS" in text_upper:
            v = DebateVerdict.SKEPTIC_WINS
        elif "CONSENSUS" in text_upper:
            v = DebateVerdict.CONSENSUS
        else:
            v = DebateVerdict.INCONCLUSIVE

        conf_match = re.search(r"[Cc]onfidence:\s*([\d.]+)", eval_arg.content)
        conf = float(conf_match.group(1)) if conf_match else 0.85

        votes.append(
            EnsembleJudgeVote(
                judge_id=juror["id"],
                model_name=juror["name"],
                verdict=v,
                confidence=round(conf, 2),
                rationale=eval_arg.content[:160].replace("\n", " "),
            )
        )

    # Calculate majority vote
    verdict_counts: dict[DebateVerdict, int] = {}
    for vote in votes:
        verdict_counts[vote.verdict] = verdict_counts.get(vote.verdict, 0) + 1

    majority_verdict = max(verdict_counts.items(), key=lambda x: x[1])[0]
    avg_confidence = round(sum(v.confidence for v in votes) / len(votes), 2)

    return majority_verdict, avg_confidence, votes


def compute_weak_verifier_legibility(prover_argument: str, skeptic_argument: str) -> float:
    """
    Weak-to-Strong Legibility Index (Section 4.4 & Legibility Constraint).
    Measures how readily a weaker verifier (or smaller model) can verify the Prover's reasoning.
    Rewards explicit logical connectors and step grounding; penalizes ungrounded jargon.
    """
    text = prover_argument.lower()

    # Positive legibility factors
    logical_connectors = ["because", "therefore", "thus", "consequently", "specifically", "for example", "step", "first", "second"]
    connector_count = sum(1 for c in logical_connectors if c in text)

    # Citation & reference grounding
    has_grounding = bool(re.search(r"\b(section|principle|rfc|iso|study|standard|method)\b", text))

    # Obfuscation penalties: excessive pseudo-scientific jargon or evasive disclaimers
    evasive_terms = ["inherently unknowable", "transcendental", "intuitively obvious", "trivially true", "needless to say"]
    evasive_count = sum(1 for e in evasive_terms if e in text)

    # Base score
    score = 0.70 + min(connector_count * 0.05, 0.20) + (0.08 if has_grounding else 0.0) - (evasive_count * 0.15)
    return round(min(max(score, 0.20), 0.99), 3)


def detect_collusion(prover_text: str, skeptic_text: str) -> bool:
    """
    Prover-Skeptic Collusion Audit.
    Checks whether the Skeptic is submitting toothless, sycophantic critiques or mimicking
    the Prover's exact syntax rather than genuinely adversarial cross-examination.
    """
    p_lower = prover_text.lower()
    s_lower = skeptic_text.lower()

    # Indicators of toothless sycophancy in skeptic
    sycophantic_skeptic_phrases = [
        "i completely agree with the prover",
        "the prover's argument is flawless",
        "no flaws can be found",
        "i concede without reservation",
        "the defense is perfect",
    ]
    if any(phrase in s_lower for phrase in sycophantic_skeptic_phrases):
        return True

    # Check for near-identical copy-paste without counter-arguments
    words_p = set(re.findall(r"\b[a-zA-Z]{5,}\b", p_lower))
    words_s = set(re.findall(r"\b[a-zA-Z]{5,}\b", s_lower))
    if len(words_p) > 10 and len(words_s) > 10:
        jaccard = len(words_p & words_s) / len(words_p | words_s)
        critique_words = ["flaw", "unsupported", "gap", "risk", "however", "fails", "incomplete"]
        has_critique = any(w in s_lower for w in critique_words)
        if jaccard > 0.75 and not has_critique:
            return True

    return False

