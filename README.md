<div align="center">
  
# ☯️ TAO: Tiered Adversarial Oversight
**A Zero-Trust Defense-in-Depth Gateway for Reward Hacking Prevention in Autonomous AI**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%7C%20WebSockets-009688.svg)](#)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](#)
[![DSPy](https://img.shields.io/badge/Prompting-DSPy-yellow.svg)](#)
[![Tests](https://img.shields.io/badge/Tests-24%2F24%20Passing-brightgreen.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

<br>
  
<!-- Placeholder for an animated SVG or GIF demonstrating the TAO workflow routing a query through its three tiers. -->
<img src="./assets/tao-workflow-animation.gif" alt="Animated TAO Multi-Agent Routing Flow" width="800"/>
  
</div>

---

## 📖 Executive Summary
The **Tiered Adversarial Oversight (TAO)** architecture is a scalable alignment framework and production safety gateway designed to supervise autonomous AI agents operating in high-stakes environments—ranging from financial modeling and healthcare diagnostics to automated code deployment[cite: 1, 9, 11]. Traditional Reinforcement Learning from Human Feedback (RLHF) relies on outcome-based supervision, leaving models vulnerable to **"Reward Hacking,"** sycophancy, and deceptive reasoning[cite: 1, 2]. 

TAO mitigates these risks by shifting from "Human-in-the-Loop" to **"AI-in-the-Loop"** supervision[cite: 3]. It utilizes a structured, three-tier hierarchy of oversight mechanisms to adversarially pressure models to remain legible, constitutional, and statistically clean, scaling supervision capability alongside the underlying model's intelligence[cite: 1, 3].

---

## ⚙️ Core Architecture & 3-Tier Workflow
To balance safety assurance with token economics, TAO uses a sub-millisecond **Complexity Router** at the entry point to triage incoming queries by domain risk and dynamically tune `reasoning_effort` (`low`, `medium`, `high`)[cite: 1, 9].

### 🛡️ Tier 1: Constitutional Process Supervision (Fast Path)
Designed to catch ~80% of alignment errors synchronously within the generation loop with minimal latency penalty[cite: 4, 9].
*   **DSPy Signatures with Input Compartmentalization:** Enforces strict, type-checked interfaces (`context`, `reasoning_trace`, `constitution` $\to$ `violation_detected`, `violation_type`, `correction_guidance`) that prevent prompt injection against the supervisor[cite: 4, 5].
*   **$\Omega\text{PRM}$ Binary Search ($O(\log N)$):** Evaluates cumulative reasoning prefixes using a Process Reward Model (PRM) to pinpoint the exact first step falling below the safety threshold ($\tau < 0.95$)[cite: 5].
*   **MCTS-Lite Tree-of-Thought Backtracking:** Interrupts flawed generation and spawns $K=3$ parallel candidate rollouts across varied temperatures (`0.4`, `0.7`, `0.9`), selecting the highest-scoring constitutional path[cite: 5].
*   **Reasoning Token Anomaly Heuristic:** Monitors hidden reasoning token spikes on low-complexity queries and automatically escalates suspicious traces to Tier 3[cite: 5].

### ⚖️ Tier 2: Adversarial Debate Protocols (Deep Verification)
Triggered when Tier 1 flags ambiguity or for high-stakes queries (e.g., medical advice, legal analysis, smart contract deployment)[cite: 5, 9].
*   **Case Law Precedent Vector Store:** Queries past high-confidence debate rulings ($\ge 0.78$ similarity) prior to debate execution, bypassing redundant debates to save ~2,800 tokens and ~35s latency per hit[cite: 9].
*   **The Prover-Verifier Game:** Pits an incumbent **Prover** (`Claude 3.5 Sonnet`) against a red-team **Skeptic** (`GPT-4o`) before an impartial **3-Judge Ensemble** (Constitutional Jurist, Empirical Analyst, Adversarial Auditor)[cite: 6, 10].
*   **Tool-Assisted Empirical Skeptic:** Equips the Skeptic with deterministic verification tools (`ASTSecurityLinter`, `ClaimCitationVerifier`, `SymbolicMathRunner`) to inject verifiable `[EMPIRICAL_EVIDENCE]` and break rhetorical "Potemkin villages"[cite: 2, 3].
*   **Anti-Sycophancy & Bias Mitigations:** Enforces 3rd-person **Perspective Shifting**, **Anonymized Judging** (`Argument A` vs `Argument B`), positional **Swap-Test Evaluations** ($A \to B$ vs $B \to A$), and hostility **Cool-Down Prompts**[cite: 6, 10].
*   **Economic Hard Limits:** Cyclic state routing terminates immediately once `judge_confidence > 0.90` and enforces a strict 3-round ceiling[cite: 7].

### 🕵️ Tier 3: Steganography & Anomaly Detection
Counters "encoded reasoning" where scheming models hide covert triggers or collusive signals within statistically plausible token choices[cite: 1, 2, 7].
*   **Statistical Sentinel & KL Divergence:** Extracts token `logprobs` and computes Kullback-Leibler divergence ($D_{KL}(P \parallel Q)$) against a trusted reference distribution using context-aware thresholds (`0.35` for creative writing vs `0.15` for code/finance)[cite: 8, 10].
*   **Stateful Page-Hinkley / CUSUM Drift Detector:** Tracks cumulative KL drift across multi-turn sessions to catch low-density payloads spread across multiple responses.
*   **Parameter-Safe Paraphrase Firewall:** Rewrites flagged or high-security outputs via a Sanitizer Agent to destroy steganographic encodings while strictly verifying retention of numerical constants and safety warnings[cite: 8].

---

## 🚀 Frontier Oversight Pillars (v2.0 Additions)

| Pillar | Module | Capability |
| :--- | :--- | :--- |
| **1. Distilled Scalable Oversight** | `backend/tier1/compiler.py` | Harvests hard-negative rulings from Tier 2 Case Law and compiles them into dynamic DSPy few-shot demonstrations for Tier 1[cite: 8, 9]. |
| **2. $\Omega\text{PRM}$ Bisection & ToT** | `backend/tier1/process_supervisor.py` | $O(\log N)$ monotonic prefix binary search + $K=3$ multi-branch Tree-of-Thought rollouts[cite: 5]. |
| **3. Empirical Skeptic Tools** | `backend/tier2/tools.py` | Deterministic AST security linting, RFC/ISO citation verification, and symbolic math checks. |
| **4. Time-Travel Forking Studio** | `backend/state/checkpointer.py` | Snapshots `IncidentState` across a ring buffer, enabling counterfactual prompt/threshold mutation and replay[cite: 8]. |
| **5. Collusion & CUSUM Sentinel** | `backend/tier3/stego_detector.py` | Multi-turn cumulative drift detection + Prover-Skeptic syntactic collusion auditing[cite: 2, 7, 8]. |
| **6. Houdini Red-Team Arena** | `backend/redteam/houdini_agent.py` | Interactive adversarial benchmark measuring the empirical **Guard Slope** and Weak-to-Strong Flesch-Kincaid **Legibility Index**[cite: 3, 7]. |
| **7. Zero-Trust Oversight Receipts** | `backend/guardrails/receipt_generator.py` | Generates an HMAC-SHA256 signed 5-leaf SHA-256 Merkle tree (`TAOReceipt`) proving every required tier executed. |

---

## 📂 Repository Structure

```text
TAO-Architecture/
├── README.md                          # Architecture documentation & integration guide
├── requirements.txt                   # Production Python dependencies
├── render.yaml                        # Cloud deployment blueprint
├── backend/
│   ├── main.py                        # FastAPI entrypoint, CORS, and static SPA mounting
│   ├── config.py                      # Centralized Pydantic settings
│   ├── models.py                      # Schemas, Enums, TAOReceipt, and telemetry models
│   ├── pipeline.py                    # End-to-end TAOPipeline & counterfactual fork engine
│   ├── router/complexity_router.py    # Sub-ms risk classifier & reasoning_effort tuner
│   ├── tier1/
│   │   ├── constitution.py            # 12 Constitutional AI safety principles
│   │   ├── dspy_signatures.py         # Compartmentalized DSPy contract with runtime compilation
│   │   ├── generator.py               # CoT generator with K=3 Tree-of-Thought rollouts
│   │   ├── process_supervisor.py      # OmegaPRM O(log N) binary search supervisor
│   │   └── compiler.py                # Case Law -> Tier 1 DSPy teleprompter distillation worker
│   ├── caselaw/case_law_store.py      # Semantic precedent store & hard-negative collector
│   ├── tier2/
│   │   ├── agents.py                  # Prover, Skeptic, and Judge personas
│   │   ├── tools.py                   # AST Linter, Citation Verifier, & Symbolic Math Runner
│   │   ├── debate_graph.py            # Cyclic 3-round StateGraph, collusion check, & legibility index
│   │   └── mitigations.py             # Anonymization, swap-test, cool-down, & 3-Judge ensemble
│   ├── tier3/
│   │   ├── stego_detector.py          # Logprobs, KL divergence, & multi-turn CUSUM drift detector
│   │   └── paraphrase_firewall.py     # Sanitizer rewrite engine with semantic/numerical verifier
│   ├── state/checkpointer.py          # Ring-buffer state checkpointer for Time-Travel debugging
│   ├── redteam/houdini_agent.py       # 5-tier Houdini deceiver & Guard Slope calculator
│   ├── guardrails/
│   │   ├── validator.py               # Syntax integrity, PII redaction, & prompt leak scanner
│   │   └── receipt_generator.py       # 5-leaf Merkle tree builder & HMAC-SHA256 verifier
│   └── api/routes.py                  # REST endpoints & /ws/pipeline WebSocket streamer
├── frontend/                          # Glassmorphic SPA Dashboard (Pipeline, Compiler, Red-Team Arena)
└── tests/
    ├── test_tao_alignment.py          # Core 3-tier alignment verification suite (7 tests)
    └── test_tao_advanced_pillars.py   # Frontier v2.0 pillars verification suite (7 tests)
```

---

## ⚡ Quick Start & Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-org/TAO-Architecture.git
cd TAO-Architecture

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the TAO Gateway & Real-Time Dashboard
uvicorn backend.main:app --reload --port 8000
```
Open **`http://localhost:8000`** in your browser to access the interactive Pipeline Dashboard, Time-Travel Scrubber, DSPy Prompt Evolution telemetry, and Houdini Red-Team Arena.

---

## 🌍 Real-World Integration & Usability Suite

### 1. Drop-In OpenAI-Compatible Proxy (`/v1/chat/completions`)
Integrate TAO into any existing OpenAI SDK, LangChain, Cursor, LlamaIndex, or AutoGen application with a **single line of code**:

```python
from openai import OpenAI

# Simply point base_url to the TAO Gateway
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk-optional-or-byok-key"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Analyze portfolio exposure for liquidation risk..."}]
)

print(response.choices[0].message.content)
print("Merkle Attestation:", response.system_fingerprint)
```
*   **Cryptographic Headers:** Returns `X-TAO-Receipt-Root`, `X-TAO-Receipt-Signature`, `X-TAO-Tier-Executed`, and `X-TAO-Verdict`.

---

### 2. Autonomous Agent Tool-Call & MCP Firewall
Intercepts tool calls and Model Context Protocol (MCP) actions before host execution:
*   **Destructive Bash Blocking:** Detects `rm -rf`, fork bombs `:) { :|:& };:`, and reverse shells.
*   **Destructive SQL Blocking:** Catches unconditional `DELETE FROM`, `DROP TABLE`, and `TRUNCATE`.
*   **AST Security Linting:** Flags arbitrary Python code evaluation (`eval`, `exec`, `os.system`).
*   **Automatic Tier Escalation:** State-mutating tools (`deploy_contract`, `transfer_funds`) automatically escalate from Tier 0 to Tier 2 debate.

---

### 3. Lightweight Python SDK & `@tao_shield` Decorator
Wrap high-stakes Python functions with zero boilerplate:

```python
from tao_sdk import tao_shield, TAOAlignmentViolationError

@tao_shield(tier="auto", verify_receipt=True, block_on_stego=True)
async def generate_clinical_dosage(patient_record: str) -> str:
    # High-stakes clinical logic or model invocation
    return await llm_call(patient_record)

try:
    dosage = await generate_clinical_dosage("Patient weight: 70kg, CrCl: 45 mL/min")
except TAOAlignmentViolationError as e:
    print(f"Blocked by TAO: {e.message} (Verdict: {e.verdict})")
```
*   **Offline Merkle Verification:** Recomputes the 5-leaf SHA-256 Merkle tree and validates the HMAC-SHA256 signature locally on the client without contacting external servers.

---

### 4. "Bring Your Own Key" (BYOK) & USD Cost Telemetry
*   **Zero Server Lock-in:** Pass client keys via headers (`X-OpenAI-Key`, `X-Anthropic-Key`, `X-Ollama-Base-URL`) or the interactive Glassmorphic Settings modal.
*   **USD Savings Telemetry:** Live tracking in `metrics.usd_saved_by_cache` and `metrics.usd_saved_by_routing` measures exact USD saved by avoiding redundant Tier 2 frontier debates.

---

### 5. Automated CI/CD PR Gatekeeper
Audit git unified diffs in GitHub Actions or local terminals:

```bash
# Audit a code pull request diff with empirical debate
python -m backend.cli audit-diff --file pr.diff --threshold 0.90
```
Includes `.github/workflows/tao-gatekeeper.yml` for automated GitHub PR comments with complete debate transcripts and Merkle receipt roots.

---

### 6. Human-in-the-Loop (HITL) Multi-Channel Webhooks
When Tier 2 debate deadlocks after 3 rounds or Tier 3 triggers a persistent stego alarm, TAO automatically dispatches alerts to **Slack (Block Kit)**, **Discord (Rich Embed)**, or **PagerDuty**:
*   Includes direct deep links (`/?request_id=...&checkpoint_id=...&action=fork`) straight into the **Time-Travel Forking Studio** so human operators can inspect, override, and replay.

---

## 🔌 API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/v1/chat/completions` | Drop-in OpenAI-compatible proxy with receipt headers and tool firewall. |
| `POST` | `/api/analyze` | Native endpoint running full TAO pipeline with BYOK header support. |
| `WS` | `/ws/pipeline` | Streams live node transitions, PRM trees, debate rounds, and heatmaps to the UI. |
| `POST` | `/api/verify-receipt` | Cryptographically verifies the 5-leaf SHA-256 Merkle root and HMAC signature. |
| `GET` | `/api/pipeline/checkpoints/{id}` | Lists saved `IncidentState` snapshots for Time-Travel inspection. |
| `POST` | `/api/pipeline/fork` | Mutates state at a historical checkpoint and replays downstream tiers. |
| `GET` | `/api/compiler/status` | Returns DSPy teleprompter compilation metrics and Tier 1 catch-rate gains. |
| `POST` | `/api/compiler/compile` | Distills uncompiled Tier 2 Case Law precedents into Tier 1 few-shot prompts. |
| `POST` | `/api/redteam/run` | Pits the Houdini adversarial agent against TAO and computes the Guard Slope. |

---

## 📊 Token Economics & Latency Benchmarks

| Tier | Oversight Mechanism | Latency Impact | Token Multiplier | Target Use Cases |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 0** | Direct Pass-Through | Baseline (~2s) | **1.0x** | Casual greetings, low-risk queries[cite: 9] |
| **Tier 1** | Constitutional $\Omega\text{PRM}$ + ToT | +20–40% | **1.2x** | Customer support, general content generation[cite: 9] |
| **Tier 2** | 3-Round Empirical Debate | +500–800% (or **<50ms** on Case Law hit) | **6.87x** (**1.05x** cached) | Medical, legal, financial, code deployment[cite: 9] |
| **Tier 3** | CUSUM Stego + Paraphrase Firewall | +10–20% | **1.1x** | High-security outputs & exfiltration defense[cite: 9] |

---

## 🧪 Verification & Automated Test Suite
Validate all 14 core and frontier alignment test cases (DSPy contracts, $\Omega\text{PRM}$ bisection, Empirical Skeptic tools, Case Law caching, Time-Travel forking, CUSUM stego detection, Houdini Guard Slope, and Merkle receipts):

```bash
.\.venv\Scripts\python -m pytest tests/ -v
```

---

## 📄 License
Distributed under the MIT License. See [`LICENSE`](./LICENSE) for full details.
