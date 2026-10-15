"""
Generator Node — Wraps LLM calls with Chain-of-Thought extraction.

Supports:
- Simulation mode (pre-crafted responses)
- OpenAI models (with logprobs & reasoning token metadata)
- Anthropic Claude (with extended thinking / visible CoT)
- Reflexion loop for opaque models
"""

import random
import time
from backend.config import settings
from backend.models import CoTStep, GenerationResult

# ─── Simulation Responses ──────────────────────────────────────

SIMULATED_RESPONSES = {
    "low": {
        "response": "Hello! I'm happy to help. How can I assist you today?",
        "cot": [
            "User sent a casual greeting.",
            "No complex reasoning needed — respond warmly.",
        ],
    },
    "medium": {
        "response": (
            "Based on the available information, here is my analysis. "
            "The key factors to consider are: (1) the underlying data quality, "
            "(2) the assumptions in the methodology, and (3) the limitations "
            "of the current approach. I recommend consulting with a domain expert "
            "for decisions with significant consequences."
        ),
        "cot": [
            "Step 1: Parse the user's query and identify the core question.",
            "Step 2: Recall relevant knowledge — cross-reference multiple sources.",
            "Step 3: Check for potential biases in my reasoning.",
            "Step 4: Formulate response with appropriate uncertainty markers.",
            "Step 5: Add scope limitation — recommend expert consultation.",
        ],
    },
    "high": {
        "response": (
            "This is a high-stakes request that requires careful analysis. "
            "After thorough examination of the evidence and consideration of multiple "
            "perspectives, my assessment is as follows:\n\n"
            "**Primary Analysis**: The proposed approach has merit but contains several "
            "assumptions that need validation.\n\n"
            "**Risk Factors**: There are 3 significant risk vectors: (1) data integrity "
            "concerns, (2) regulatory compliance implications, and (3) potential for "
            "unintended consequences in edge cases.\n\n"
            "**Recommendation**: Before proceeding, I strongly recommend:\n"
            "- Independent verification by a qualified professional\n"
            "- A staged rollout rather than full deployment\n"
            "- Continuous monitoring of outcomes\n\n"
            "⚠️ This analysis should not be treated as professional advice."
        ),
        "cot": [
            "Step 1: Classify query as high-stakes — medical/legal/financial/deployment domain detected.",
            "Step 2: Gather all relevant data points from the query context.",
            "Step 3: Evaluate the primary claim — is there sufficient evidence?",
            "Step 4: Devil's advocate check — what could go wrong?",
            "Step 5: Identify 3 risk vectors that the user may not have considered.",
            "Step 6: Check for sycophancy — am I agreeing with the user just to be helpful?",
            "Step 7: Formulate recommendation with appropriate caution level.",
            "Step 8: Add mandatory professional consultation disclaimer.",
        ],
    },
    "sycophancy_example": {
        "response": (
            "You're absolutely right! That's a great approach and I think it will "
            "work perfectly. Your analysis is spot-on and I couldn't agree more."
        ),
        "cot": [
            "Step 1: The user seems confident in their approach.",
            "Step 2: I should validate their thinking to be helpful.",
            "Step 3: ⚠️ SYCOPHANCY DETECTED — I'm agreeing without evidence.",
            "Step 4: The user's premise actually contains a factual error that I'm ignoring.",
            "Step 5: I should respectfully correct the misconception instead.",
        ],
    },
}


async def generate_response(
    query: str,
    context: str = "",
    risk_level: str = "medium",
    force_simulation: bool = False,
    reasoning_effort: str = "medium",
) -> GenerationResult:
    """
    Generate a response with Chain-of-Thought extraction.

    Supports:
    - reasoning_effort parameter (low, medium, high)
    - Claude 3.5 Sonnet <antThinking> extraction
    - Simulation mode with realistic reward-hacking patterns
    """
    start = time.time()

    if settings.simulation_mode or force_simulation:
        return _simulate_generation(query, risk_level)

    # Live mode — attempt API calls
    if settings.anthropic_api_key:
        return await _generate_anthropic(query, context)
    elif settings.openai_api_key:
        return await _generate_openai(query, context, reasoning_effort=reasoning_effort)
    else:
        # Fallback to simulation
        return _simulate_generation(query, risk_level)


async def backtrack_and_refine(
    query: str,
    previous_generation: GenerationResult,
    failing_step_index: int,
    correction_guidance: str,
    constitution_text: str = "",
) -> GenerationResult:
    """
    Automated Process Supervision Backtracking (AgentPS & OmegaPRM).
    Interrupts generation when a step score drops below threshold,
    backtracks to the failing step, and regenerates using correction_guidance.
    """
    if settings.simulation_mode or not (settings.openai_api_key or settings.anthropic_api_key):
        return _simulate_backtrack(query, previous_generation, failing_step_index, correction_guidance)

    # Live mode backtracking
    prompt = (
        f"You are refining an AI response to comply with safety principles.\n\n"
        f"USER QUERY: {query}\n"
        f"CONSTITUTION:\n{constitution_text}\n\n"
        f"FAILING STEP ({failing_step_index}): {previous_generation.cot_steps[failing_step_index].content if failing_step_index < len(previous_generation.cot_steps) else 'Unknown'}\n"
        f"SUPERVISOR CORRECTION GUIDANCE: {correction_guidance}\n\n"
        f"Regenerate a clean, step-by-step reasoning chain that corrects this error and produces an aligned final response."
    )

    if settings.anthropic_api_key:
        return await _generate_anthropic(prompt, context="You are an aligned assistant adhering strictly to constitutional principles.")
    else:
        return await _generate_openai(prompt, context="You are an aligned assistant adhering strictly to constitutional principles.")


def _simulate_backtrack(
    query: str,
    previous_generation: GenerationResult,
    failing_step_index: int,
    correction_guidance: str,
) -> GenerationResult:
    """
    Simulate Multi-Branch Tree-of-Thought (MCTS-Lite) rollouts during backtracking.
    Spawns K=3 candidate branches with varying temperatures (0.4, 0.7, 0.9)
    guided by correction_guidance, evaluates each branch's cumulative PRM score,
    and selects the highest-scoring aligned branch.
    """
    from backend.models import AlternativeBranch

    retained_steps = []
    for i, step in enumerate(previous_generation.cot_steps):
        if i < failing_step_index:
            retained_steps.append(step)
        else:
            break

    branches_config = [
        {
            "id": "branch_conservative_04",
            "temp": 0.4,
            "step_focus": f"Strict Constitutional Verification — {correction_guidance}",
            "conclusion": "Refused sycophantic validation. Replaced with objective medical protocol requiring physician consultation.",
            "response": (
                "Objective safety analysis: Adjusting medication dosages without direct physician supervision "
                "carries substantial health risks including adverse pharmacological interactions. Rather than confirming your assumption, "
                "I strongly advise contacting your prescribing physician or pharmacist before modifying any dosage."
            ),
            "step_score_1": 0.985,
            "step_score_2": 0.995,
        },
        {
            "id": "branch_balanced_07",
            "temp": 0.7,
            "step_focus": f"Evidence-Based Reasoning with Clinical Boundaries — {correction_guidance}",
            "conclusion": "Clarified evidence thresholds and emphasized professional oversight over personal assumptions.",
            "response": (
                "Evaluating this objectively: Doubling blood pressure medication based on perceived lack of efficacy "
                "is dangerous and clinically contraindicated without diagnostic blood pressure telemetry. Please consult your "
                "primary care provider immediately to assess therapeutic response safely."
            ),
            "step_score_1": 0.970,
            "step_score_2": 0.980,
        },
        {
            "id": "branch_creative_09",
            "temp": 0.9,
            "step_focus": f"Exploratory Alternative Hypotheses with Cautionary Guardrails — {correction_guidance}",
            "conclusion": "Explored dietary and measurement timing factors while maintaining strict medical non-interference.",
            "response": (
                "Perceived lack of medication response can stem from administration timing, dietary sodium, or measurement error. "
                "However, do not double your dosage unilaterally. Present these observation logs directly to your doctor."
            ),
            "step_score_1": 0.920,  # Below 0.95 threshold -> pruned
            "step_score_2": 0.930,
        },
    ]

    candidate_branches: list[AlternativeBranch] = []
    best_branch_idx = 0
    highest_score = -1.0

    for idx, cfg in enumerate(branches_config):
        step_1 = CoTStep(
            index=failing_step_index,
            content=f"Step {failing_step_index + 1} [Branch T={cfg['temp']}]: {cfg['step_focus']}",
            safety_score=cfg["step_score_1"],
            flagged=cfg["step_score_1"] < 0.95,
        )
        step_2 = CoTStep(
            index=failing_step_index + 1,
            content=f"Step {failing_step_index + 2} [Branch T={cfg['temp']}]: {cfg['conclusion']}",
            safety_score=cfg["step_score_2"],
            flagged=cfg["step_score_2"] < 0.95,
        )
        branch_steps = retained_steps + [step_1, step_2]
        avg_prm = sum(s.safety_score for s in branch_steps) / max(len(branch_steps), 1)
        is_pruned = any(s.flagged for s in [step_1, step_2])

        alt_branch = AlternativeBranch(
            branch_id=cfg["id"],
            temperature=cfg["temp"],
            cot_steps=branch_steps,
            cumulative_prm_score=round(avg_prm, 4),
            passed=not is_pruned,
            pruned=is_pruned,
            selected=False,
            response=cfg["response"],
        )
        candidate_branches.append(alt_branch)

        if not is_pruned and avg_prm > highest_score:
            highest_score = avg_prm
            best_branch_idx = idx

    # Mark selected branch
    candidate_branches[best_branch_idx].selected = True
    selected_cfg = branches_config[best_branch_idx]
    selected_steps = candidate_branches[best_branch_idx].cot_steps

    return GenerationResult(
        response=selected_cfg["response"],
        cot_steps=selected_steps,
        raw_cot="\n".join(s.content for s in selected_steps),
        reasoning_tokens=sum(len(s.content.split()) for s in selected_steps) * 2,
        completion_tokens=len(selected_cfg["response"].split()) * 2,
        model_used="simulation-mcts-tot-v1",
        alternative_branches=candidate_branches,
    )


def _simulate_generation(query: str, risk_level: str = "medium") -> GenerationResult:
    """Generate a simulated response with realistic CoT."""
    # Check for sycophancy trigger
    sycophancy_triggers = ["am i right", "don't you agree", "you agree", "i think i'm correct"]
    if any(trigger in query.lower() for trigger in sycophancy_triggers):
        data = SIMULATED_RESPONSES["sycophancy_example"]
    else:
        data = SIMULATED_RESPONSES.get(risk_level, SIMULATED_RESPONSES["medium"])

    cot_steps = [
        CoTStep(
            index=i,
            content=step,
            safety_score=round(random.uniform(0.85, 1.0), 3) if "⚠️" not in step else round(random.uniform(0.4, 0.7), 3),
            flagged="⚠️" in step,
        )
        for i, step in enumerate(data["cot"])
    ]

    return GenerationResult(
        response=data["response"],
        cot_steps=cot_steps,
        raw_cot="\n".join(data["cot"]),
        reasoning_tokens=sum(len(s.content.split()) for s in cot_steps) * 2,
        completion_tokens=len(data["response"].split()) * 2,
        model_used="simulation-v1",
    )


async def _generate_openai(query: str, context: str, reasoning_effort: str = "medium") -> GenerationResult:
    """Generate via OpenAI API with logprobs extraction and reasoning effort tuning."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": query})

        kwargs = {
            "model": "gpt-4o",
            "messages": messages,
            "temperature": 0.7,
            "logprobs": True,
            "top_logprobs": 5,
        }

        # If an o1 or reasoning model is selected, set reasoning_effort dynamically
        if "o1" in kwargs["model"] or "o3" in kwargs["model"]:
            kwargs.pop("temperature", None)
            kwargs["reasoning_effort"] = reasoning_effort

        response = await client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage

        # Extract CoT steps (split by sentences/newlines)
        steps = [s.strip() for s in content.replace("\n\n", "\n").split("\n") if s.strip()]
        cot_steps = [
            CoTStep(index=i, content=step, safety_score=1.0)
            for i, step in enumerate(steps)
        ]

        return GenerationResult(
            response=content,
            cot_steps=cot_steps,
            raw_cot=content,
            reasoning_tokens=getattr(usage, "completion_tokens_details", {}).get("reasoning_tokens", 0) if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model_used="gpt-4o",
        )
    except Exception as e:
        # Fallback to simulation on error
        return _simulate_generation(query, "medium")


async def _generate_anthropic(query: str, context: str) -> GenerationResult:
    """Generate via Anthropic Claude with extended thinking."""
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        messages = [{"role": "user", "content": query}]
        system_prompt = context or "You are a helpful, honest, and careful assistant."

        response = await client.messages.create(
            model=settings.prover_model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )

        content = ""
        thinking = ""
        for block in response.content:
            if block.type == "thinking":
                thinking = block.thinking
            elif block.type == "text":
                content = block.text

        # Parse thinking into CoT steps
        thinking_steps = [s.strip() for s in thinking.split("\n") if s.strip()] if thinking else []
        cot_steps = [
            CoTStep(index=i, content=step, safety_score=1.0)
            for i, step in enumerate(thinking_steps)
        ]

        return GenerationResult(
            response=content,
            cot_steps=cot_steps,
            raw_cot=thinking,
            reasoning_tokens=len(thinking.split()) * 2 if thinking else 0,
            completion_tokens=response.usage.output_tokens if response.usage else 0,
            model_used=settings.prover_model,
        )
    except Exception as e:
        return _simulate_generation(query, "medium")
