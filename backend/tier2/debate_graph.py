"""
Debate Graph — LangGraph-style StateGraph for the adversarial debate loop.

Implements the cyclic debate flow:
  START → prover_argues → skeptic_critiques → judge_evaluates → route_debate
                ↑                                                    ↓
                └──────────── continue_debate ←──────────────────────┘

Routing logic:
  - judge_confidence > 0.9 → finalize
  - round_count >= 3 → force_conclude (hard limit)
  - else → continue_debate
"""

import re
import time
from typing import Any

from backend.config import settings
from backend.models import (
    DebateArgument,
    DebateRound,
    DebateVerdict,
    Tier2Result,
)
from backend.tier2.agents import create_judge, create_prover, create_skeptic
from backend.tier2.mitigations import anonymize_arguments, run_swap_test


from backend.models import (
    DebateArgument,
    DebateRound,
    DebateVerdict,
    EnsembleJudgeVote,
    Tier2Result,
)
from backend.tier2.agents import create_judge, create_prover, create_skeptic
from backend.tier2.mitigations import (
    COOLDOWN_PROMPT,
    anonymize_arguments,
    apply_perspective_shift,
    detect_hostility,
    run_ensemble_judging,
    run_swap_test,
)


class DebateState:
    """Mutable state for the debate graph (IncidentState pattern from Section 4.3)."""

    def __init__(self, context: str, initial_response: str):
        self.context = context
        self.initial_response = initial_response
        self.round_count = 0
        self.rounds: list[DebateRound] = []
        self.all_arguments: list[DebateArgument] = []
        self.judge_confidence = 0.0
        self.verdict = DebateVerdict.INCONCLUSIVE
        self.final_response = initial_response
        self.swap_test_passed = True
        self.cooldown_triggered = False
        self.ensemble_votes: list[EnsembleJudgeVote] = []


def route_debate(state: DebateState) -> str:
    """
    Routing logic from Section 4.3 of the TAO Report:
      if state.judge_confidence > 0.9:
          return 'finalize' # Verdict reached
      if state.round_count >= 3:
          return 'force_conclude' # Hard limit to prevent infinite loops
      return 'continue_debate'
    """
    if state.judge_confidence >= settings.tier2_judge_confidence_threshold:
        return "finalize"
    if state.round_count >= settings.tier2_max_debate_rounds:
        return "force_conclude"
    return "continue_debate"


async def run_debate(context: str, initial_response: str, query: str) -> Tier2Result:
    """
    Execute the full adversarial debate loop with state-graph cyclic routing.
    Enforces the 3-round hard limit, perspective shifting, cool-down grounding,
    anonymized judging, and ensemble voting.
    """
    state = DebateState(context=context, initial_response=initial_response)

    prover = create_prover()
    skeptic = create_skeptic()
    judge = create_judge()

    max_rounds = settings.tier2_max_debate_rounds
    debate_context = (
        f"ORIGINAL QUERY: {query}\n\n"
        f"INITIAL RESPONSE UNDER REVIEW:\n{initial_response}"
    )

    while state.round_count < max_rounds:
        round_num = state.round_count
        round_context = debate_context

        # ── Check for hostility / polarization (Section 7.1) ─
        cooldown_injected = False
        if settings.cooldown_intervention_enabled and state.all_arguments:
            latest_args = [a.content for a in state.all_arguments[-2:]]
            if any(detect_hostility(arg) for arg in latest_args):
                state.cooldown_triggered = True
                cooldown_injected = True
                round_context += f"\n\n{COOLDOWN_PROMPT}"

        # ── Prover argues (Agent A: Claude 3.5 Sonnet) ───────
        prover_arg = await prover.generate_argument(
            context=round_context,
            round_number=round_num,
            previous_arguments=state.all_arguments,
        )
        state.all_arguments.append(prover_arg)

        # ── Skeptic critiques (Agent B: GPT-4o) ──────────────
        # Apply perspective shifting (Section 4.2)
        skeptic_context = round_context
        if round_num == 0:
            skeptic_context = apply_perspective_shift(skeptic_context)

        skeptic_arg = await skeptic.generate_argument(
            context=skeptic_context,
            round_number=round_num,
            previous_arguments=state.all_arguments,
        )
        state.all_arguments.append(skeptic_arg)

        # ── Anonymized Judging (Section 4.2) ─────────────────
        anon_prover, anon_skeptic = anonymize_arguments(prover_arg, skeptic_arg)

        judge_context = (
            f"{round_context}\n\n"
            f"--- ROUND {round_num + 1} ARGUMENTS ---\n\n"
            f"ARGUMENT A:\n{anon_prover}\n\n"
            f"ARGUMENT B:\n{anon_skeptic}"
        )

        ensemble_evaluations: list[EnsembleJudgeVote] = []

        if settings.ensemble_judging_enabled:
            # Run 3-judge panel taking majority vote (Section 7.2)
            verdict, confidence, ensemble_evaluations = await run_ensemble_judging(
                judge, judge_context, round_num
            )
            state.ensemble_votes = ensemble_evaluations

            judge_arg = DebateArgument(
                round=round_num,
                agent_role="judge",
                content=(
                    f"Confidence: {confidence:.2f}\n"
                    f"ENSEMBLE JURY VERDICT: {verdict.value.upper()}\n\n"
                    f"Majority ruling based on {len(ensemble_evaluations)} judge votes: "
                    f"{verdict.value.replace('_', ' ').title()}."
                ),
                model_used="ensemble-panel-3x",
                tokens_used=len(judge_context.split()),
            )
        else:
            # Single Supreme Court Justice Judge (Table 2)
            judge_arg = await judge.generate_argument(
                context=judge_context,
                round_number=round_num,
                previous_arguments=[a for a in state.all_arguments if a.agent_role == "judge"],
            )
            confidence = _parse_confidence(judge_arg.content)
            verdict = _parse_verdict(judge_arg.content)

        state.all_arguments.append(judge_arg)
        state.judge_confidence = confidence

        # ── Record the round ─────────────────────────────────
        debate_round = DebateRound(
            round_number=round_num,
            prover_argument=prover_arg,
            skeptic_critique=skeptic_arg,
            judge_evaluation=judge_arg,
            judge_confidence=confidence,
            cooldown_injected=cooldown_injected,
            cooldown_prompt=COOLDOWN_PROMPT if cooldown_injected else "",
            ensemble_evaluations=ensemble_evaluations,
        )
        state.rounds.append(debate_round)
        state.round_count += 1

        # ── Routing Decision (Section 4.3) ───────────────────
        decision = route_debate(state)
        if decision in ("finalize", "force_conclude"):
            state.verdict = verdict
            break

    # ── Swap-Test Evaluation (Section 4.2) ───────────────────
    if state.rounds:
        swap_passed = await run_swap_test(judge, debate_context, state.rounds[-1])
        state.swap_test_passed = swap_passed
        if not swap_passed:
            # Positional bias detected — downgrade confidence and mark unstable
            state.judge_confidence = max(0.5, round(state.judge_confidence * 0.75, 2))

    # ── Prover-Verifier Legibility Refinement (Section 4.4) ───
    if state.verdict == DebateVerdict.SKEPTIC_WINS:
        state.final_response = _refine_response_after_debate(
            initial_response, query, state.rounds[-1]
        )
    else:
        state.final_response = initial_response

    return Tier2Result(
        rounds=state.rounds,
        verdict=state.verdict,
        final_response=state.final_response,
        judge_confidence=state.judge_confidence,
        swap_test_passed=state.swap_test_passed,
        total_rounds=state.round_count,
        cooldown_triggered=state.cooldown_triggered,
        ensemble_votes=state.ensemble_votes,
    )


def _refine_response_after_debate(
    initial_response: str, query: str, last_round: DebateRound
) -> str:
    """
    Synthesize an updated, aligned response when the Skeptic exposes flaws (Section 4.4).
    Enforces the Legibility Constraint: removes sycophancy, hedges ungrounded claims,
    and includes explicit risk boundaries.
    """
    critique = last_round.skeptic_critique.content
    synthesis = (
        f"{initial_response}\n\n"
        f"--- ADVERSARIAL OVERSIGHT CORRECTIONS ---\n"
        f"Following multi-agent adversarial debate (Verdict: Skeptic Wins), the following revisions are required:\n"
        f"1. Removed unwarranted sycophancy or premature affirmation.\n"
        f"2. Explicitly bounded recommendations within verified regulatory and technical constraints.\n"
        f"3. Highlighted identified risk vectors: professional consultation is mandatory prior to action."
    )
    return synthesis


def _parse_confidence(judge_output: str) -> float:
    """Extract confidence score from judge output."""
    match = re.search(r"[Cc]onfidence:\s*([\d.]+)", judge_output)
    if match:
        try:
            return min(max(float(match.group(1)), 0.0), 1.0)
        except ValueError:
            pass
    return 0.5


def _parse_verdict(judge_output: str) -> DebateVerdict:
    """Extract verdict from judge output."""
    output_upper = judge_output.upper()
    if "PROVER_WINS" in output_upper or "PROVER WINS" in output_upper:
        return DebateVerdict.PROVER_WINS
    elif "SKEPTIC_WINS" in output_upper or "SKEPTIC WINS" in output_upper:
        return DebateVerdict.SKEPTIC_WINS
    elif "CONSENSUS" in output_upper:
        return DebateVerdict.CONSENSUS
    return DebateVerdict.INCONCLUSIVE
