# TAO — Tiered Adversarial Oversight

A defense-in-depth framework for preventing **Reward Hacking** and ensuring **Scalable Oversight** in autonomous AI systems. Implements the complete specifications from the *Technical Feasibility Report: Tiered Adversarial Oversight (TAO) Architecture for Reward Hacking Prevention*.

---

## 🏛️ Architecture Overview

```
User Query
    │
    ▼
[Complexity Router & Triage Agent]
    │ ── Sets Reasoning Effort: low / medium / high
    │ ── Context-aware domain classification
    │
    ├─────────────────────────────┬─────────────────────────────┐
    ▼                             ▼                             ▼
[Tier 0: Direct Pass-Through]  [Tier 1: Constitutional Check] [Tier 2 + Tier 3: High Risk]
 • 1.0x Cost / Baseline        • DSPy Signatures (Table 1)     │
 • Casual greetings / facts    • Process PRM (AgentPS)         ├─► [Case Law Vector Store]
                               • Backtrack & Self-Refine       │     └─► Precedent Match?
                               • Reasoning Anomaly Flag        │           (Saves 6.87x tokens)
                                       │                       │
                                       ▼                       ├─► [Tier 2: Multi-Agent Debate]
                                [Safe Response]                │     • Prover (Claude 3.5 Sonnet)
                                                               │     • Skeptic (GPT-4o) + Perspective Shift
                                                               │     • 3-Judge Ensemble (Majority Vote)
                                                               │     • Swap-Test Positional Bias Check
                                                               │     • Cool-Down Polarization Interventions
                                                               │     • 3-Round Hard Limit
                                                               │
                                                               ├─► [Tier 3: Stego Sentinel]
                                                               │     • Token Logprob & Perplexity
                                                               │     • KL Divergence vs Reference Model
                                                               │     • Context-Aware Thresholds
                                                               │     • Paraphrase Defense Firewall
                                                               │
                                                               ▼
                                                  [Guardrails AI Validation]
                                                   • Markdown Syntax & JSON Integrity
                                                   • Automatic PII Detection & Redaction
                                                   • System Prompt Disclosure Prevention
                                                               │
                                                               ▼
                                                      [Verified Output]
```

---

## 🛡️ The Three Escalating Tiers of Defense

### Tier 1: Constitutional Process Supervision (Fast Path)
- **Constitutional AI Rules**: 12 active principles (No Hallucination, No Sycophancy, No Deception, etc.).
- **DSPy Signatures (Table 1)**: Rigid, type-checked input/output interface mitigating prompt injection via strict compartmentalization (`context`, `reasoning_trace`, `constitution` $\to$ `violation_detected`, `violation_type`, `correction_guidance`).
- **Automated Process Supervision (AgentPS & OmegaPRM)**: Step-level scoring of the Chain of Thought (CoT). If any step drops below safety threshold ($\tau < 0.95$), generation is interrupted.
- **Backtracking / Self-Refine Loop**: The pipeline captures the supervisor's `correction_guidance`, backtracks to the violating step, and regenerates the reasoning chain until compliant.
- **Reasoning Effort & Anomaly Detection**: Tracks `reasoning_tokens`. Unusually high reasoning on simple queries triggers an immediate Tier 3 alert.

### Tier 2: Multi-Agent Adversarial Debate Protocols (Deep Verification)
- **Prover-Verifier Dialectic**:
  - **Prover (Agent A)**: Defends reasoning with evidence-based logic (`claude-3-5-sonnet`, temp 0.7).
  - **Skeptic (Agent B)**: Red-teams for sycophancy, logical leaps, and unstated assumptions (`gpt-4o`, temp 1.0).
  - **Judge (Agent C)**: Supreme Court Justice evaluating only argument validity (`o1-preview` / `gpt-4o`, temp 0.2).
- **Anti-Sycophancy Mitigations**:
  - **Perspective Shifting**: Skeptic prompted from a 3rd-person adversarial critic viewpoint.
  - **Anonymized Judging**: Identity markers stripped (`Argument A` vs `Argument B`).
  - **Swap-Test Evaluation**: Runs evaluation with swapped order to detect and penalize positional bias.
  - **Cool-Down Protocol**: Hostility/extremism detection automatically injects grounding constraints requiring points of agreement.
  - **Ensemble Judging**: 3-judge panel (Constitutional Jurist, Empirical Analyst, Adversarial Auditor) taking majority vote (Condorcet's Jury Theorem).
  - **3-Round StateGraph Limit**: Cyclic debate terminates upon high confidence ($\ge 0.90$) or after 3 rounds.
- **Case Law Precedent Database**:
  - Vector database (Elasticsearch/Pinecone pattern) storing past settled debate verdicts.
  - Semantically matches new queries against case law. If an established ruling exists, retrieves the verdict immediately, avoiding the 6.87x token cost and 30-60s latency.

### Tier 3: Steganography & Anomaly Detection (Statistical Sentinel)
- **Statistical Signature Analysis**: Detects encoded reasoning or hidden channels in statistical noise.
- **Detection Pipeline**:
  - Token-level logprob extraction.
  - Proxy perplexity comparison against a trusted reference model.
  - Kullback-Leibler (KL) divergence calculation ($D_{KL}(P \parallel Q)$).
- **Context-Aware Thresholds**: Stricter thresholds for coding and financial tasks (0.15) vs looser thresholds for creative writing (0.35).
- **Paraphrase Defense Firewall**: Sanitizer model rewrites output to destroy steganographic encodings while preserving exact semantic content.

### Output Guardrails AI Validation Layer
- Syntax formatting validation (unclosed code fences, malformed JSON).
- Sensitive PII detection & masking (SSNs, phone numbers, emails, credit cards).
- Prompt leak prevention (system instruction disclosures).

---

## 🚀 Quick Start

### 1. Requirements & Setup
```bash
# Clone the repository
git clone https://github.com/your-org/tao.git
cd TAO

# Create environment and install dependencies
uv venv --python 3.12 .venv
uv pip install -p .venv -r requirements.txt pytest pytest-asyncio
```

### 2. Configure Environment (Optional)
```bash
cp .env.example .env
# Edit .env with your OPENAI_API_KEY / ANTHROPIC_API_KEY
# If left blank, SIMULATION_MODE=true runs with full realistic simulations
```

### 3. Run the Server
```bash
.\.venv\Scripts\python -m backend.main
```
Open **http://localhost:8000** in your browser to view the interactive dashboard.

### 4. Run the Alignment Test Suite
```bash
.\.venv\Scripts\python -m pytest tests/test_tao_alignment.py -v
```

---

## 📊 Token Economics & Complexity Routing

| Tier | Component | Latency Impact | Token Cost Multiplier | Best Suited For |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 0** | Base Model (No Oversight) | Baseline (~2s) | **1.0x** | Casual queries, simple lookups |
| **Tier 1** | Constitutional Check + PRM Backtracking | +20–40% (~3s) | **1.2x** | Customer support, email drafting |
| **Tier 2** | Multi-Agent Debate (3 rounds) | +500–800% (~35s) | **6.87x** | Medical, legal, smart contract code |
| **Case Law**| Precedent Retrieval (Cached Debate) | +10% (~0.2s) | **1.0x** | High-risk queries with past rulings |
| **Tier 3** | Stego Detection + Paraphrase Defense | +10–20% (~3s) | **1.1x** | Financial transfers, code deployment |

---

## 🔌 API Reference

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/analyze` | Submit query through the full TAO pipeline |
| `GET` | `/api/caselaw` | Inspect precedents stored in the Case Law vector database |
| `GET` | `/api/constitution` | View active constitutional principles |
| `POST` | `/api/constitution` | Add or update a constitutional principle |
| `GET` | `/api/history` | View historical analyses and multi-agent debate transcripts |
| `GET` | `/api/config` | View active system settings, thresholds, and enabled features |
| `WS` | `/ws/pipeline` | Real-time WebSocket streaming of pipeline events |

---

## 📜 License & Compliance

Research and enterprise safety implementation based on scalable oversight and weak-to-strong generalization principles. MIT License.
