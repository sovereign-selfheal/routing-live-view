"""Parse the `[policy-router] {...}` log lines of the router into page events.

The line is a stable interface of the router repo (AGENTS.md §2.4): a Python dict literal with at
least `policy`, `requested`, `routed_to`, `decided_by`, `chain`, `reason`, `team`. Since router
v0.11.0 (namespace policy on) it also has `ns_restricted`, `ns_source`, `namespaces` and
`ns_labels_loaded`. The page reads metadata only: the line has no prompt text.
"""

from __future__ import annotations

import ast
from typing import Any

PREFIX = "[policy-router] "
MAX_LINE = 20000


def split_timestamp(line: str) -> tuple[str, str]:
    """Split a log line read with `timestamps=true` into (RFC3339 time, text)."""
    head, sep, rest = line.partition(" ")
    if sep and len(head) >= 20 and head[4:5] == "-" and "T" in head:
        return head, rest
    return "", line


def parse_line(line: str, sota_alias: str = "sota-smart") -> dict[str, Any] | None:
    """One routing decision from a log line, or None for any other line."""
    if len(line) > MAX_LINE:
        return None
    ts, text = split_timestamp(line.rstrip("\n"))
    idx = text.find(PREFIX)
    if idx < 0:
        return None
    payload = text[idx + len(PREFIX):].strip()
    if not payload.startswith("{"):
        return None  # other router lines: metrics, labels, budget
    try:
        decision = ast.literal_eval(payload)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None
    if not isinstance(decision, dict) or "routed_to" not in decision:
        return None
    routed_to = str(decision.get("routed_to") or "")
    reason = str(decision.get("reason") or "")
    decided_by = decision.get("decided_by") or (
        "fail-closed" if "fail-closed" in reason else "unknown")
    return {
        "ts": ts,
        "routed_to": routed_to,
        "destination": "external" if routed_to == sota_alias else "local",
        "decided_by": str(decided_by),
        "team": decision.get("team"),
        "namespaces": _names(decision.get("namespaces")),
        "ns_restricted": _names(decision.get("ns_restricted")),
        "ns_source": decision.get("ns_source"),
        "prompt_chars": decision.get("prompt_chars"),
        "trace_id": decision.get("trace_id"),
        "reason": reason[:240],
    }


def _names(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v) for v in value if isinstance(v, str)][:20]
