"""Shared finish gate for visual critique results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["PASS", "FAIL"]


@dataclass
class QualityGateState:
    """In-memory finish gate state for the active canvas."""

    last_verdict: Verdict | None = None
    last_critique: str | None = None
    blocked_by_failure: bool = False
    drew_after_failure: bool = False
    mark_piece_done_accepted: bool = False


_state = QualityGateState()


def reset_quality_gate() -> None:
    """Reset finish gate state for a fresh canvas/session."""
    _state.last_verdict = None
    _state.last_critique = None
    _state.blocked_by_failure = False
    _state.drew_after_failure = False
    _state.mark_piece_done_accepted = False


def note_drawing(paths_count: int) -> None:
    """Record that the agent drew a revision after a failed critique."""
    if paths_count <= 0:
        return
    if _state.blocked_by_failure:
        _state.drew_after_failure = True
    elif _state.last_verdict == "PASS":
        _state.last_verdict = None
        _state.last_critique = None


def parse_critique_verdict(text: str) -> Verdict | None:
    """Parse the critique verdict line."""
    match = re.search(r"(?im)^VERDICT:\s*(PASS|FAIL)\b", text)
    if match is None:
        return None
    return match.group(1).upper()  # type: ignore[return-value]


def record_critique_result(text: str) -> Verdict:
    """Record critique result and return the effective verdict."""
    verdict = parse_critique_verdict(text) or "FAIL"
    _state.last_verdict = verdict
    _state.last_critique = text[:2000]
    _state.mark_piece_done_accepted = False
    if verdict == "FAIL":
        _state.blocked_by_failure = True
        _state.drew_after_failure = False
        return "FAIL"
    _state.blocked_by_failure = False
    _state.drew_after_failure = False
    return "PASS"


def finish_block_message() -> str | None:
    """Return why finish tools are blocked, if they are blocked."""
    if _state.blocked_by_failure:
        if _state.drew_after_failure:
            return (
                "Finish blocked: the last critique returned VERDICT: FAIL. "
                "You drew a revision, but must call view_canvas and critique_canvas again. "
                "Only VERDICT: PASS clears this gate."
            )
        return (
            "Finish blocked: the last critique returned VERDICT: FAIL. "
            "Draw a substantive revision, call view_canvas, then call critique_canvas again. "
            "Only VERDICT: PASS clears this gate."
        )
    if _state.last_verdict != "PASS":
        return (
            "Finish blocked: call view_canvas and critique_canvas first. "
            "Only VERDICT: PASS opens the finish gate for signing, naming, or marking done."
        )
    return None


def record_mark_piece_done_attempt(accepted: bool) -> None:
    """Record whether mark_piece_done was accepted by the tool."""
    _state.mark_piece_done_accepted = accepted


def consume_mark_piece_done_accepted() -> bool:
    """Return and clear the latest accepted mark_piece_done state."""
    accepted = _state.mark_piece_done_accepted
    _state.mark_piece_done_accepted = False
    return accepted


def get_quality_gate_snapshot() -> dict[str, object]:
    """Return observable finish-gate state."""
    return {
        "last_verdict": _state.last_verdict,
        "blocked_by_failure": _state.blocked_by_failure,
        "drew_after_failure": _state.drew_after_failure,
        "last_critique": _state.last_critique,
    }


def is_finish_gate_blocked() -> bool:
    """Return whether a failed critique is currently blocking finish."""
    return _state.blocked_by_failure


def quality_gate_prompt_context() -> str | None:
    """Return finish-gate context for the next agent turn."""
    if not _state.blocked_by_failure:
        return None
    critique = (_state.last_critique or "").strip()
    lines = [
        "Finish gate is blocked by the last visual critique.",
        f"Last verdict: {_state.last_verdict or 'UNKNOWN'}",
        f"Drew after failure: {_state.drew_after_failure}",
    ]
    if critique:
        lines.append("Last critique:")
        lines.append(critique[:1600])
    lines.append(
        "Binding next step: make a structural revision that directly fixes the critique "
        "(change shapes and values, not just surface texture), then call view_canvas and "
        "critique_canvas again. Do not sign, name, or mark done until critique_canvas "
        "returns VERDICT: PASS."
    )
    return "\n".join(lines)


def critique_gate_message(verdict: Verdict) -> str:
    """Message appended to critique output so the agent sees the binding state."""
    if verdict == "PASS":
        return "FINISH GATE: OPEN. You may sign, name, and mark done when satisfied."
    return (
        "FINISH GATE: BLOCKED. Do not sign, name, or mark done. "
        "Make a structural revision that addresses the critique, view the canvas, "
        "then call critique_canvas again."
    )
