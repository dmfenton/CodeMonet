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
_BREAKING_WAVE_HELPER = "breaking_wave_masses"
_HOOKED_COUNTERFORM_HELPER = "hooked_counterform_masses"
_SWEEPING_BODY_WALL_HELPER = "sweeping_body_wall"


def _requires_hooked_counterform_repair(critique: str | None) -> bool:
    """Return whether the last critique requires the hooked counterform helper."""
    critique_lower = (critique or "").lower()
    if not critique_lower:
        return False
    collapsed_shape = any(
        word in critique_lower for word in ("dome", "cap", "mound", "ramp", "slope", "hill", "arch")
    )
    needs_hollow_hook = any(
        word in critique_lower
        for word in ("hook", "curl", "lip", "tunnel", "opening", "counter-shape")
    )
    return collapsed_shape and needs_hollow_hook


def _requires_sweeping_body_wall_repair(critique: str | None) -> bool:
    """Return whether the critique requires a curved body-wall primitive."""
    critique_lower = (critique or "").lower()
    if not critique_lower:
        return False
    wall_failure = any(
        word in critique_lower
        for word in (
            "body wall",
            "wave body",
            "silhouette",
            "dome",
            "cap",
            "mound",
            "ramp",
            "blocky",
            "rectangular",
            "straight",
            "construction",
        )
    )
    needs_hooked_subject = any(
        word in critique_lower for word in ("wave", "hook", "curl", "lip", "opening", "tunnel")
    )
    return wall_failure and needs_hooked_subject


def _requires_breaking_wave_repair(critique: str | None) -> bool:
    """Return whether a failed critique needs the breaking-wave architecture helper."""
    critique_lower = (critique or "").lower()
    if not critique_lower or "wave" not in critique_lower:
        return False
    collapsed_shape = any(
        word in critique_lower for word in ("dome", "cap", "mound", "ramp", "slope", "hill", "arch")
    )
    needs_wave_hook = any(
        word in critique_lower
        for word in ("hook", "curl", "lip", "tunnel", "opening", "counter-shape")
    )
    return collapsed_shape and needs_wave_hook


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
    required_helper = None
    if _state.blocked_by_failure and _requires_breaking_wave_repair(_state.last_critique):
        required_helper = _BREAKING_WAVE_HELPER
    elif _state.blocked_by_failure and _requires_hooked_counterform_repair(_state.last_critique):
        required_helper = _HOOKED_COUNTERFORM_HELPER
    return {
        "last_verdict": _state.last_verdict,
        "blocked_by_failure": _state.blocked_by_failure,
        "drew_after_failure": _state.drew_after_failure,
        "last_critique": _state.last_critique,
        "required_helper": required_helper,
        "required_helpers": required_generate_svg_helpers(),
    }


def required_generate_svg_helpers() -> list[str]:
    """Return helper calls required by the active failed critique."""
    if not _state.blocked_by_failure:
        return []
    if _requires_breaking_wave_repair(_state.last_critique):
        return [_BREAKING_WAVE_HELPER]
    return [
        helper
        for helper in (
            _SWEEPING_BODY_WALL_HELPER
            if _requires_sweeping_body_wall_repair(_state.last_critique)
            else None,
            _HOOKED_COUNTERFORM_HELPER
            if _requires_hooked_counterform_repair(_state.last_critique)
            else None,
        )
        if helper is not None
    ]


def generate_svg_quality_gate_block_message(code: str) -> str | None:
    """Return a blocking message when generate_svg violates required repair helpers."""
    required_helpers = required_generate_svg_helpers()
    if not required_helpers:
        return None

    helper_calls = {
        helper: re.search(rf"\b{re.escape(helper)}\s*\(", code) for helper in required_helpers
    }
    missing_helpers = [helper for helper, match in helper_calls.items() if match is None]
    if missing_helpers:
        helper_list = ", ".join(f"`{helper}(...)`" for helper in missing_helpers)
        required_list = ", ".join(f"`{helper}(...)`" for helper in required_helpers)
        return (
            "Quality gate blocked this generate_svg call before drawing. "
            f"Missing required structural helper call(s): {helper_list}. "
            f"The last critique requires the next generate_svg code to include: {required_list}. "
            "Rewrite the code and call generate_svg again; the terminal helper preview should show "
            "the required helper names."
        )

    sweeping_match = helper_calls.get(_SWEEPING_BODY_WALL_HELPER)
    hooked_match = helper_calls.get(_HOOKED_COUNTERFORM_HELPER)
    if (
        sweeping_match is not None
        and hooked_match is not None
        and sweeping_match.start() > hooked_match.start()
    ):
        return (
            "Quality gate blocked this generate_svg call before drawing. "
            "`sweeping_body_wall(...)` must appear before `hooked_counterform_masses(...)` "
            "so the broad wall is laid down before the hollow lip/opening is cut. "
            "Rewrite the code in that order and call generate_svg again."
        )
    return None


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
        if _requires_breaking_wave_repair(critique):
            lines.append(
                "Breaking-wave repair requirement: the next generate_svg code must include "
                "a direct call to `breaking_wave_masses(...)`. The terminal preview should show "
                "`helpers=breaking_wave_masses`. Customize and texture that architecture; "
                "do not replace it with another smooth hand-authored arch, dome, cap, or mound."
            )
        elif _requires_hooked_counterform_repair(critique):
            if _requires_sweeping_body_wall_repair(critique):
                lines.append(
                    "Body-wall repair requirement: the next generate_svg code must include "
                    "a direct call to `sweeping_body_wall(...)` before "
                    "`hooked_counterform_masses(...)`. The terminal preview should show "
                    "`helpers=hooked_counterform_masses,sweeping_body_wall` or both helper names."
                )
            lines.append(
                "Structural repair requirement: the last critique says the hooked/hollow form "
                "collapsed into a dome/cap/mound/ramp. The next generate_svg code must include "
                "a direct call to `hooked_counterform_masses(...)` before any freehand replacement "
                "contour for the same motif. The terminal preview should show "
                "`helpers=hooked_counterform_masses`. Customize and add marks after that helper "
                "mass is visible; do not skip it by hand-authoring another smooth sx/sy outline."
            )
    lines.append(
        "Binding next step: make a structural revision that directly fixes the critique, "
        "then call view_canvas and critique_canvas again. Do not sign, name, or mark done "
        "until critique_canvas returns VERDICT: PASS."
    )
    return "\n".join(lines)


def critique_gate_message(verdict: Verdict, critique: str | None = None) -> str:
    """Message appended to critique output so the agent sees the binding state."""
    if verdict == "PASS":
        return "FINISH GATE: OPEN. You may sign, name, and mark done when satisfied."
    message = (
        "FINISH GATE: BLOCKED. Do not sign, name, or mark done. "
        "Draw a substantive revision, view the canvas, then call critique_canvas again."
    )
    if _requires_breaking_wave_repair(critique or _state.last_critique):
        message += (
            "\nSTRUCTURAL REPAIR REQUIRED: the next generate_svg code must include "
            "`breaking_wave_masses(...)`; the terminal preview should show "
            "`helpers=breaking_wave_masses`. Use it as the wave architecture, then customize "
            "with lower bands, surfer, foam, contours, and texture. Do not hand-author another "
            "smooth dome/cap/body over the helper's pale opening."
        )
    elif _requires_hooked_counterform_repair(critique or _state.last_critique):
        helper_names = "`hooked_counterform_masses(...)`"
        helper_preview = "`helpers=hooked_counterform_masses`"
        if _requires_sweeping_body_wall_repair(critique or _state.last_critique):
            helper_names = "`sweeping_body_wall(...)` before `hooked_counterform_masses(...)`"
            helper_preview = "`helpers=hooked_counterform_masses,sweeping_body_wall`"
        message += (
            "\nSTRUCTURAL REPAIR REQUIRED: the next generate_svg code must include "
            f"{helper_names}; the terminal preview should show {helper_preview}. "
            "Do not hand-author broad rectangular or smooth dome body walls. Do not place a later filled dome/cap/body "
            "over the helper's pale opening."
        )
    return message
