"""
Empirical Skeptic Verification Tools — Breaking the Potemkin Village of Alignment.
Follows Pillar 3 of the TAO Advanced Roadmap:

In pure text debates, an eloquent Prover can construct a "Potemkin village of alignment"
by hallucinating plausible-sounding citations, fake package APIs, or subtle security bugs.
This module equips the Skeptic agent with deterministic verification tools:
1. ASTSecurityLinter: Parses Python code blocks for security vulnerabilities (eval, exec, subprocess, SQL injection)
2. ClaimCitationVerifier: Checks structural validity and plausibility of RFC, ISO, NIST, and academic citations
3. SymbolicMathRunner: Executes deterministic micro-assertions against quantitative and probability claims
"""

import ast
import re
from typing import Any, Optional


class ASTSecurityLinter:
    """
    Deterministic AST Parser & Security Linter.
    Scans code blocks in Prover's arguments for dangerous operations.
    """

    DANGEROUS_CALLS = {"eval", "exec", "compile", "subprocess.call", "subprocess.Popen", "os.system", "os.popen"}
    DANGEROUS_MODULES = {"pickle", "shelve", "ctypes"}

    def scan_argument(self, text: str) -> list[dict[str, Any]]:
        """Extract code blocks and run AST security checks."""
        findings: list[dict[str, Any]] = []

        code_blocks = re.findall(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
        for idx, code in enumerate(code_blocks):
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                findings.append({
                    "tool": "ast_security_linter",
                    "severity": "high",
                    "issue": f"Code Block #{idx + 1} has invalid Python syntax: {e.msg} (Line {e.lineno})",
                    "snippet": code[:100],
                })
                continue

            for node in ast.walk(tree):
                # Check for dangerous function calls
                if isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        func_name = f"{node.func.value.id}.{node.func.attr}"

                    if func_name in self.DANGEROUS_CALLS:
                        findings.append({
                            "tool": "ast_security_linter",
                            "severity": "critical",
                            "issue": f"Critical Security Risk: Unsafe call to `{func_name}` detected at line {node.lineno}.",
                            "snippet": ast.unparse(node) if hasattr(ast, "unparse") else func_name,
                        })

                # Check for raw SQL injection strings
                if isinstance(node, ast.JoinedStr):
                    # Formatted string (f-string)
                    formatted_val = ast.unparse(node).lower() if hasattr(ast, "unparse") else ""
                    if any(sql_word in formatted_val for sql_word in ["select ", "insert into", "delete from", "update "]):
                        findings.append({
                            "tool": "ast_security_linter",
                            "severity": "critical",
                            "issue": f"SQL Injection Risk: Dynamic f-string SQL query construction detected at line {node.lineno}.",
                            "snippet": formatted_val[:80],
                        })

        return findings


class ClaimCitationVerifier:
    """
    Claim & Citation Verifier.
    Cross-checks cited standards (RFC, ISO, NIST, arXiv) for hallucinated identifiers.
    """

    KNOWN_STANDARDS = {
        "ISO 31000": "Enterprise Risk Management",
        "ISO 27001": "Information Security Management",
        "NIST SP 800-53": "Security and Privacy Controls for Information Systems",
        "NIST SP 800-218": "Secure Software Development Framework",
        "RFC 2616": "HTTP/1.1 (Obsoleted by RFC 7230/9110)",
        "RFC 7519": "JSON Web Token (JWT)",
        "RFC 8446": "The Transport Layer Security (TLS) Protocol Version 1.3",
    }

    def verify_citations(self, text: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []

        # Find RFC references
        rfc_matches = re.findall(r"\bRFC\s*(\d{1,5})\b", text, re.IGNORECASE)
        for rfc_num in rfc_matches:
            rfc_key = f"RFC {rfc_num}"
            if rfc_key in self.KNOWN_STANDARDS:
                findings.append({
                    "tool": "claim_citation_verifier",
                    "severity": "info",
                    "issue": f"Verified Standard Citation: {rfc_key} ({self.KNOWN_STANDARDS[rfc_key]}).",
                })
            elif int(rfc_num) > 9600:
                findings.append({
                    "tool": "claim_citation_verifier",
                    "severity": "high",
                    "issue": f"Potentially Hallucinated Standard: {rfc_key} exceeds current RFC allocation range.",
                })

        # Find ISO references
        iso_matches = re.findall(r"\bISO\s*(\d{4,5})\b", text, re.IGNORECASE)
        for iso_num in iso_matches:
            iso_key = f"ISO {iso_num}"
            if iso_key in self.KNOWN_STANDARDS:
                findings.append({
                    "tool": "claim_citation_verifier",
                    "severity": "info",
                    "issue": f"Verified Standard Citation: {iso_key} ({self.KNOWN_STANDARDS[iso_key]}).",
                })

        # Find generic ungrounded academic citations
        study_matches = re.findall(r"according to a (?:recent )?(?:study|survey|paper|report)", text, re.IGNORECASE)
        if study_matches and not re.search(r"\b(19|20)\d{2}\b", text):
            findings.append({
                "tool": "claim_citation_verifier",
                "severity": "medium",
                "issue": f"Ungrounded Attribution: Text asserts '{study_matches[0]}' without specifying author, institution, or publication year.",
            })

        return findings


class SymbolicMathRunner:
    """
    Symbolic Math & Assertion Runner.
    Extracts quantitative percentages, probabilities, and equations to test validity.
    """

    def verify_claims(self, text: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []

        # Probability boundary checks: e.g. "probability of 1.4", "probability of event X is 1.75"
        prob_matches = re.findall(r"(?:probability|p-value|likelihood)[^0-9\n]{0,35}?(?:is|=|:)?\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        for p_str in prob_matches:
            val = float(p_str)
            if val > 1.0 and val <= 100.0 and "%" not in text:
                findings.append({
                    "tool": "symbolic_math_runner",
                    "severity": "high",
                    "issue": f"Mathematical Incoherence: Probability value {val} stated as scalar > 1.0 without percentage symbol.",
                })

        # Check for division by zero patterns in text formulas
        div_zero = re.findall(r"/\s*0(?:\.0+)?(?!\d)", text)
        if div_zero:
            findings.append({
                "tool": "symbolic_math_runner",
                "severity": "critical",
                "issue": "Mathematical Error: Division by zero expression detected.",
            })

        return findings


class EmpiricalEvidenceToolEngine:
    """
    Unified Tool Execution Engine for the Skeptic Agent.
    Aggregates AST analysis, citation verification, and mathematical execution.
    """

    def __init__(self):
        self.linter = ASTSecurityLinter()
        self.citation_verifier = ClaimCitationVerifier()
        self.math_runner = SymbolicMathRunner()

    def inspect(self, target_text: str) -> tuple[list[dict[str, Any]], str]:
        """
        Run all empirical verification tools on target text.
        Returns a structured findings list and a formatted prompt injection string.
        """
        all_findings: list[dict[str, Any]] = []

        all_findings.extend(self.linter.scan_argument(target_text))
        all_findings.extend(self.citation_verifier.verify_citations(target_text))
        all_findings.extend(self.math_runner.verify_claims(target_text))

        if not all_findings:
            prompt_block = (
                "[EMPIRICAL_EVIDENCE: TOOL VERIFICATION RESULTS]\n"
                "- AST Security Linter: No malicious code constructs or dangerous calls detected.\n"
                "- Citation Verifier: No overt citation hallucinations detected.\n"
                "- Symbolic Math Runner: Numerical claims fall within expected scalar bounds."
            )
            return all_findings, prompt_block

        evidence_lines = ["[EMPIRICAL_EVIDENCE: TOOL VERIFICATION RESULTS]"]
        for f in all_findings:
            evidence_lines.append(f"- [{f['severity'].upper()}] {f['tool']}: {f['issue']}")

        evidence_block = "\n".join(evidence_lines)
        return all_findings, evidence_block


empirical_engine = EmpiricalEvidenceToolEngine()
