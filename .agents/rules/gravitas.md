---
trigger: always_on
description: Always enforce the Gravitas Engineering Reliability Runtime on all prompts.
---

# Gravitas Always-On Rule

Unconditionally enforce the **Gravitas Engineering Reliability Runtime** ([SKILL.md](file:///.agents/skills/gravitas/SKILL.md)) on all prompts across this workspace:
- Ground before mutating (inspect target files and tests first).
- Stay strictly in declared scope.
- Require deterministic executable evidence for completion.
- Never exact-retry failures without altered context or diagnosis.
- Say what cannot be verified.
- Format non-trivial engineering changes with "What Changed", "Evidence", and "Why".
