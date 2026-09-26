"""Finish gate for visual critique results, owned by one agent's tool context."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["PASS", "FAIL"]

_CRITIQUE_HISTORY = 3

# After this many consecutive FAILs, additive revision has demonstrably
# stopped working — the gate switches to "repaint, don't accrete" orders.
OVERWORK_FAILURE_THRESHOLD = 3

REPAINT_DIRECTIVE = (
    "OVERWORK ALERT: multiple consecutive critiques have failed. Adding more "
    "marks is making the painting worse, not better. You cannot scrape paint "
    "off, but you CAN repaint: cover the failed region (or the whole canvas) "
    "with opaque filled masses (fill_opacity=1.0) that restate the 2-4 big "
    "value shapes cleanly, then add ONE restrained pass of marks. Simplify the "
    "composition if needed. Do not add texture to mud."
)


def parse_critique_verdict(text: str) -> Verdict | None:
    """Parse the critique verdict line."""
    match = re.search(r"(?im)^VERDICT:\s*(PASS|FAIL)\b", text)
    if match is None:
        return None
    return match.group(1).upper()  # type: ignore[return-value]


@dataclass
class QualityGateState:
    """Finish gate state for one agent's active piece."""

    last_verdict: Verdict | None = None
    last_critique: str | None = None
    blocked_by_failure: bool = False
    drew_after_failure: bool = False
    mark_piece_done_accepted: bool = False
    consecutive_failures: int = 0
    # Earlier critiques of this piece, oldest first, so the critic stays consistent
    history: list[str] = field(default_factory=list)

    def reset(self) -> None:
        """Reset finish gate state for a fresh canvas/session."""
        self.last_verdict = None
        self.last_critique = None
        self.blocked_by_failure = False
        self.drew_after_failure = False
        self.mark_piece_done_accepted = False
        self.consecutive_failures = 0
        self.history = []

    def critique_history(self) -> list[str]:
        """Earlier critiques of the current piece, oldest first."""
        return list(self.history)

    def note_drawing(self, paths_count: int) -> None:
        """Record new marks: a revision after a FAIL, or a change that voids a PASS."""
        if paths_count <= 0:
            return
        if self.blocked_by_failure:
            self.drew_after_failure = True
        elif self.last_verdict == "PASS":
            self.last_verdict = None
            self.last_critique = None

    def record_critique_result(self, text: str) -> Verdict:
        """Record critique result and return the effective verdict."""
        verdict = parse_critique_verdict(text) or "FAIL"
        self.last_verdict = verdict
        self.last_critique = text[:2000]
        self.history = [*self.history, text[:2000]][-_CRITIQUE_HISTORY:]
        self.mark_piece_done_accepted = False
        if verdict == "FAIL":
            self.blocked_by_failure = True
            self.drew_after_failure = False
            self.consecutive_failures += 1
            return "FAIL"
        self.blocked_by_failure = False
        self.drew_after_failure = False
        self.consecutive_failures = 0
        return "PASS"

    def finish_block_message(self) -> str | None:
        """Return why finish tools are blocked, if they are blocked."""
        if self.blocked_by_failure:
            if self.drew_after_failure:
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
        if self.last_verdict != "PASS":
            return (
                "Finish blocked: call view_canvas and critique_canvas first. "
                "Only VERDICT: PASS opens the finish gate for signing, naming, or marking done."
            )
        return None

    def record_mark_piece_done_attempt(self, accepted: bool) -> None:
        """Record whether mark_piece_done was accepted by the tool."""
        self.mark_piece_done_accepted = accepted

    def consume_mark_piece_done_accepted(self) -> bool:
        """Return and clear the latest accepted mark_piece_done state."""
        accepted = self.mark_piece_done_accepted
        self.mark_piece_done_accepted = False
        return accepted

    def snapshot(self) -> dict[str, object]:
        """Return observable finish-gate state."""
        return {
            "last_verdict": self.last_verdict,
            "blocked_by_failure": self.blocked_by_failure,
            "drew_after_failure": self.drew_after_failure,
            "last_critique": self.last_critique,
            "consecutive_failures": self.consecutive_failures,
        }

    def is_blocked(self) -> bool:
        """Return whether a failed critique is currently blocking finish."""
        return self.blocked_by_failure

    def prompt_context(self) -> str | None:
        """Return finish-gate context for the next agent turn."""
        if not self.blocked_by_failure:
            return None
        critique = (self.last_critique or "").strip()
        lines = [
            "Finish gate is blocked by the last visual critique.",
            f"Last verdict: {self.last_verdict or 'UNKNOWN'}",
            f"Drew after failure: {self.drew_after_failure}",
        ]
        if critique:
            lines.append("Last critique:")
            lines.append(critique[:1600])
        if self.consecutive_failures >= OVERWORK_FAILURE_THRESHOLD:
            lines.append(REPAINT_DIRECTIVE)
        lines.append(
            "Binding next step: make a structural revision that directly fixes the critique "
            "(change shapes and values, not just surface texture), then call view_canvas and "
            "critique_canvas again. Do not sign, name, or mark done until critique_canvas "
            "returns VERDICT: PASS."
        )
        return "\n".join(lines)

    def critique_gate_message(self, verdict: Verdict) -> str:
        """Message appended to critique output so the agent sees the binding state."""
        if verdict == "PASS":
            return "FINISH GATE: OPEN. You may sign, name, and mark done when satisfied."
        message = (
            "FINISH GATE: BLOCKED. Do not sign, name, or mark done. "
            "Make a structural revision that addresses the critique, view the canvas, "
            "then call critique_canvas again."
        )
        if self.consecutive_failures >= OVERWORK_FAILURE_THRESHOLD:
            message += f"\n{REPAINT_DIRECTIVE}"
        return message
