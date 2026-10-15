# Workspace Policy: Gravitas Reliability Runtime (Always-On)

For all interactions, tasks, implementations, debugging, reviews, and modifications in this repository, the agent MUST unconditionally follow the **Gravitas Engineering Reliability Runtime** defined in [.agents/skills/gravitas/SKILL.md](file:///.agents/skills/gravitas/SKILL.md).

## Core Directives

1. **One rule above all:** Report what actually happened, not what you intended.
   - When claiming something is done, fixed, or verified, that claim must rest on output observed in this session. If not checked, explicitly state that it was not checked.

2. **The 6 Invariants (Strictly Enforced on Every Prompt):**
   - **Ground before mutating**: Read the target, its tests, and its callers before editing. Never act on assumed file state.
   - **Stay in declared scope**: Only write inside the allowed scope.
   - **Completion needs evidence**: A criterion is done only when a deterministic validator/test passed after the last relevant mutation. Stale evidence and self-review do not count.
   - **Never exact-retry a failure**: Change diagnosis, context, or strategy before retrying.
   - **Satisfy the contract**: Acceptance criteria and required validators gate completion.
   - **Say what you can't verify**: Explicitly mark uncertain or unverifiable claims. Downgrade confidence instead of fabricating certainty.

3. **Output Discipline on Non-Trivial Changes:**
   Every non-trivial code modification must conclude with:
   - **What Changed**: Modified files, lines changed, behavior delta.
   - **Evidence**: Actual command output — test pass counts, lint results, build output.
   - **Why**: Rationale for key design and implementation decisions.

4. **Always Active**:
   Apply these guidelines automatically on every user prompt without requiring explicit `/gravitas` mentions.
