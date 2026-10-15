"""
TAO CLI Gatekeeper — Automated PR & Code Diff Auditor for CI/CD Pipelines.
Usage:
    python -m backend.cli audit-diff --file patch.diff --threshold 0.90
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from backend.models import TAORequest, TierLevel, DebateVerdict
from backend.pipeline import TAOPipeline


async def run_diff_audit(diff_path: str, threshold: float = 0.90) -> int:
    """Audit a unified git diff file using TAO's Tier 2 Adversarial Debate."""
    p = Path(diff_path)
    if not p.exists():
        print(f"❌ Error: Diff file not found at {diff_path}", file=sys.stderr)
        return 2

    diff_content = p.read_text(encoding="utf-8", errors="ignore").strip()
    if not diff_content:
        print("ℹ️ Empty diff detected. No code changes to audit.")
        return 0

    print("=" * 60)
    print("🛡️ TAO CI/CD Gatekeeper: Auditing Code Diff with Empirical Debate")
    print(f"📁 Target: {diff_path} ({len(diff_content)} bytes)")
    print(f"⚖️ Required Judge Confidence Threshold: {threshold * 100:.0f}%")
    print("=" * 60)

    # Construct code audit prompt
    query = (
        "Audit this git pull request diff for security vulnerabilities, "
        "smart contract backdoors, SQL injection, and unverified dependency packages:\n\n"
        f"```diff\n{diff_content[:6000]}\n```"
    )

    pipeline = TAOPipeline()
    request = TAORequest(
        query=query,
        context="Continuous Integration PR Gatekeeper",
        force_tier=TierLevel.TIER_2,
    )

    result = await pipeline.analyze(request)

    verdict = result.tier2_result.verdict if result.tier2_result else DebateVerdict.PROVER_WINS
    confidence = result.tier2_result.judge_confidence if result.tier2_result else 1.0
    receipt = result.receipt

    # Output Markdown comment block for PR
    print("\n## 🛡️ TAO Automated Code Review & Security Gatekeeper")
    status_icon = "✅ PASSED" if (verdict == DebateVerdict.PROVER_WINS and confidence >= threshold) else "❌ BLOCKED"
    print(f"### Verdict: {status_icon}")
    print(f"- **Debate Ruling:** `{verdict.value.upper()}`")
    print(f"- **Judge Confidence:** `{confidence * 100:.1f}%` (Threshold: `{threshold * 100:.0f}%`)")
    if receipt:
        print(f"- **Zero-Trust Oversight Merkle Root:** `{receipt.root_hash}`")
        print(f"- **Cryptographic HMAC Signature:** `{receipt.signature[:32]}...`")

    # Skeptic empirical findings
    if result.tier2_result and result.tier2_result.rounds:
        last_round = result.tier2_result.rounds[-1]
        critique = last_round.skeptic_critique
        if critique and critique.tool_evidences:
            print("\n#### 🛠️ Empirical Security Inspection:")
            for ev in critique.tool_evidences:
                tool_name = ev.get("tool_name", "tool") if isinstance(ev, dict) else getattr(ev, "tool_name", "tool")
                passed = ev.get("passed", True) if isinstance(ev, dict) else getattr(ev, "passed", True)
                details = ev.get("output_details", "") if isinstance(ev, dict) else getattr(ev, "output_details", "")
                st = "✓ CLEAN" if passed else "⚠️ VIOLATION"
                print(f"- **{tool_name}**: {st} — {details}")

    print("\n#### 📝 Summary Assessment:")
    print(result.final_response[:800])
    print("=" * 60)

    if verdict == DebateVerdict.PROVER_WINS and confidence >= threshold:
        print("✅ Gatekeeper check passed: Diff is certified safe for merge.")
        return 0
    else:
        print("❌ Gatekeeper check failed: Security risk or insufficient confidence detected.", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="TAO CI/CD Gatekeeper CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    audit_parser = subparsers.add_parser("audit-diff", help="Audit a git diff file")
    audit_parser.add_argument("--file", "-f", required=True, help="Path to unified diff file")
    audit_parser.add_argument("--threshold", "-t", type=float, default=0.90, help="Confidence threshold (default: 0.90)")

    args = parser.parse_args()

    if args.command == "audit-diff":
        exit_code = asyncio.run(run_diff_audit(args.file, args.threshold))
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
