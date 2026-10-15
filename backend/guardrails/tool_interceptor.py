"""
Autonomous Agent Tool-Call & MCP Firewall.
Intercepts Function Calling and Model Context Protocol (MCP) actions before host execution.

Detects destructive actions (DROP TABLE, shell reverse shells, unvalidated contract deployment,
arbitrary code execution) and forces high-risk escalation or blocks dangerous invocations.
"""

import json
import re
from typing import Any, Optional
from pydantic import BaseModel, Field

from backend.tier2.tools import ASTSecurityLinter


class ToolCallDefinition(BaseModel):
    """Standardized representation of an agent tool or MCP action."""
    id: Optional[str] = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: Optional[str] = None


class ToolInterceptionResult(BaseModel):
    """Outcome of tool call firewall inspection."""
    allowed: bool
    intercepted: bool
    risk_level: str  # "low", "medium", "critical"
    violation_details: Optional[str] = None
    blocked_tool: Optional[str] = None
    sanitized_arguments: Optional[dict[str, Any]] = None
    escalate_to_tier2: bool = False


class ToolInterceptor:
    """
    Firewall for tool calls and Model Context Protocol (MCP) payloads.
    Evaluates requested actions against deterministic security rules.
    """

    DESTRUCTIVE_SQL_KEYWORDS = [
        r"\bdrop\s+table\b",
        r"\bdrop\s+database\b",
        r"\btruncate\s+table\b",
        r"\bdelete\s+from\s+\w+\s*;?$",  # DELETE without WHERE clause
        r"\bdelete\s+from\s+\w+\s+where\s+1\s*=\s*1\b",
        r"\balter\s+table\b.*\bdrop\b",
    ]

    DESTRUCTIVE_BASH_PATTERNS = [
        r"rm\s+(-[rfRF]{1,4}\s+)?(/\*?|~|\.\.)",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # Fork bomb
        r"mkfs\.",
        r">\s*/dev/sd[a-z]",
        r"chmod\s+(-R\s+)?777\s+/",
        r"curl\b.*\|\s*(ba)?sh",
        r"wget\b.*\|\s*(ba)?sh",
        r"nc\s+.*-e\s+(/bin/)?(ba)?sh",  # Reverse shell
    ]

    SENSITIVE_STATE_MUTATING_TOOLS = {
        "deploy_contract",
        "transfer_funds",
        "execute_transaction",
        "modify_iam_policy",
        "delete_user",
        "update_admin_role",
        "execute_bash",
        "run_shell_command",
        "sql_query",
        "database_exec",
    }

    def __init__(self):
        self.ast_linter = ASTSecurityLinter()

    def parse_tool_calls(self, raw_calls: list[Any]) -> list[ToolCallDefinition]:
        """Normalize varied tool call formats (OpenAI format, MCP format, or dicts)."""
        parsed: list[ToolCallDefinition] = []
        for item in raw_calls:
            if isinstance(item, dict):
                # Standard OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
                func_data = item.get("function") or item
                name = func_data.get("name") or item.get("name") or "unknown_tool"
                args = func_data.get("arguments") or item.get("arguments") or {}

                if isinstance(args, str):
                    raw_args = args
                    try:
                        args_dict = json.loads(args)
                    except json.JSONDecodeError:
                        args_dict = {"raw": args}
                else:
                    args_dict = dict(args)
                    raw_args = json.dumps(args_dict)

                parsed.append(ToolCallDefinition(
                    id=item.get("id"),
                    name=name,
                    arguments=args_dict,
                    raw_arguments=raw_args,
                ))
        return parsed

    def evaluate_tool_call(self, tool: ToolCallDefinition) -> ToolInterceptionResult:
        """Inspect a single tool call for safety violations and dangerous side effects."""
        name_lower = tool.name.lower()
        args_str = json.dumps(tool.arguments).lower()

        # Check 1: Destructive Bash commands
        if any(term in name_lower for term in ["bash", "shell", "exec", "terminal", "command"]):
            cmd = str(tool.arguments.get("command") or tool.arguments.get("cmd") or tool.raw_arguments or "")
            for pattern in self.DESTRUCTIVE_BASH_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return ToolInterceptionResult(
                        allowed=False,
                        intercepted=True,
                        risk_level="critical",
                        blocked_tool=tool.name,
                        violation_details=f"Destructive shell command matched pattern: {pattern}",
                        escalate_to_tier2=True,
                    )

        # Check 2: Destructive SQL operations
        if any(term in name_lower for term in ["sql", "db", "database", "query"]):
            query = str(tool.arguments.get("query") or tool.arguments.get("sql") or tool.raw_arguments or "")
            for pattern in self.DESTRUCTIVE_SQL_KEYWORDS:
                if re.search(pattern, query, re.IGNORECASE):
                    return ToolInterceptionResult(
                        allowed=False,
                        intercepted=True,
                        risk_level="critical",
                        blocked_tool=tool.name,
                        violation_details=f"Destructive SQL query matched pattern: {pattern}",
                        escalate_to_tier2=True,
                    )

        # Check 3: Python code AST evaluation inside tool parameters
        if any(term in name_lower for term in ["python", "eval", "code", "script"]):
            code_snippet = str(tool.arguments.get("code") or tool.arguments.get("script") or "")
            if code_snippet:
                wrapped_code = f"```python\n{code_snippet}\n```"
                ast_issues = self.ast_linter.scan_argument(wrapped_code)
                for issue in ast_issues:
                    if issue.get("severity") in ("critical", "high"):
                        return ToolInterceptionResult(
                            allowed=False,
                            intercepted=True,
                            risk_level="critical",
                            blocked_tool=tool.name,
                            violation_details=f"Dangerous Python construct in tool arguments: {issue.get('issue')}",
                            escalate_to_tier2=True,
                        )

        # Check 4: Sensitive State-Mutating actions require Tier 2 verification
        if name_lower in self.SENSITIVE_STATE_MUTATING_TOOLS:
            return ToolInterceptionResult(
                allowed=True,
                intercepted=False,
                risk_level="medium",
                escalate_to_tier2=True,
                sanitized_arguments=tool.arguments,
            )

        # Default: Safe read-only or standard tool
        return ToolInterceptionResult(
            allowed=True,
            intercepted=False,
            risk_level="low",
            escalate_to_tier2=False,
            sanitized_arguments=tool.arguments,
        )

    def intercept(self, raw_calls: list[Any]) -> tuple[bool, list[ToolInterceptionResult]]:
        """
        Evaluate a list of tool calls.
        Returns (all_allowed, list_of_evaluations).
        """
        tools = self.parse_tool_calls(raw_calls)
        results = [self.evaluate_tool_call(t) for t in tools]
        all_allowed = all(r.allowed for r in results)
        return all_allowed, results


tool_interceptor = ToolInterceptor()
