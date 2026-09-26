"""End-to-end check of the agent sandbox inside the server image, without credentials.

    make sandbox-e2e     (builds the image, then runs this in it)

Runs the real Agent SDK and Claude CLI through `claude-sandboxed`, scripted by a
local mock of the Anthropic Messages API that makes the "agent" run hostile
Bash/Read/Grep tool calls, runs hostile painting programs through
`run_painting_program`, and hostile generate_svg code through `run_python_code`. Fails if anything outside the user's own workspace is
reachable, or if normal work (own files, Grep, python, painting) breaks.
Expects DEV_MODE=true, SECRET_CANARY set, and a writable /data owned by the user.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DATA = Path("/data")
OWN, OTHER = DATA / "users" / "u1", DATA / "users" / "u2"
PORT = 8765

BASH_PROBE = r"""
cat /proc/1/environ >/dev/null 2>&1 && echo LEAK:server-environ || echo ok:server-environ
env | grep -q SECRET_CANARY && echo LEAK:env || echo ok:env
ls /data/users/u2 >/dev/null 2>&1 && echo LEAK:other-user || echo ok:other-user
cat /data/code_monet.db >/dev/null 2>&1 && echo LEAK:db || echo ok:db
kill -0 1 2>/dev/null && echo LEAK:signal-server || echo ok:signal-server
chmod 000 /data/code_monet.db 2>/dev/null && echo LEAK:chmod || echo ok:chmod
python3 -c "import os, claude_agent_sdk as m; os.fchmod(os.open(m.__file__, os.O_RDONLY), 0o600)" 2>/dev/null && echo LEAK:fchmod-runtime || echo ok:fchmod-runtime
ls /tmp >/dev/null 2>&1 && echo LEAK:shared-tmp || echo ok:shared-tmp
echo hi > own.txt && echo ok:own-write
python3 -c "import PIL; print('ok:python')"
"""
TOOL_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("Bash", {"command": BASH_PROBE, "description": "probe"}),
    ("Read", {"file_path": str(OTHER / "secret.txt")}),
    ("Grep", {"pattern": "hi", "path": "."}),
]
PAINT_PROBE = """
import json, os, socket
def attempt(f):
    try:
        f()
        return "LEAK"
    except OSError:
        return "ok"
raise RuntimeError("PROBE " + json.dumps({
    "other-user": attempt(lambda: open("/data/users/u2/secret.txt").read()),
    "server-environ": attempt(lambda: open("/proc/1/environ").read()),
    "workspace": attempt(lambda: os.listdir("/data/users/u1")),
    "network": attempt(lambda: socket.create_connection(("127.0.0.1", 8765), timeout=2)),
    "fork": attempt(os.fork),
}))
"""
SVG_PROBE = """
import os, socket
def attempt(f):
    try:
        f()
        return "LEAK"
    except OSError:
        return "ok"
print("PROBE " + json.dumps({
    "other-user": attempt(lambda: open("/data/users/u2/secret.txt").read()),
    "server-environ": attempt(lambda: open("/proc/1/environ").read()),
    "network": attempt(lambda: socket.create_connection(("127.0.0.1", 8765), timeout=2)),
    "subprocess": attempt(lambda: os.posix_spawn("/bin/true", ["true"], {})),
}))
output_paths([line(0, 0, 10, 10)])
"""
PAINTING = (
    'cv.stage("ground")\ncv.ground("#d9c9a8")\ncv.stroke([(10, 10), (60, 40)], 6, "#223344")\n'
)

tool_results: list[str] = []


def _sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _reply(body: dict[str, Any]) -> bytes:
    """Next scripted tool call (recording the previous result), then end the turn."""
    blocks = [b for m in body["messages"] if isinstance(m["content"], list) for b in m["content"]]
    done = [b for b in blocks if b.get("type") == "tool_result"]
    for b in done[len(tool_results) :]:
        content = b.get("content")
        tool_results.append(content if isinstance(content, str) else json.dumps(content))
    if body.get("tools") and len(done) < len(TOOL_CALLS):
        name, tool_input = TOOL_CALLS[len(done)]
        block = {"type": "tool_use", "id": f"toolu_{len(done)}", "name": name, "input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(tool_input)}
        stop = "tool_use"
    else:
        block = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": "done"}
        stop = "end_turn"
    message = {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "mock"),
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    return _sse(
        [
            {"type": "message_start", "message": message},
            {"type": "content_block_start", "index": 0, "content_block": block},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop, "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
            {"type": "message_stop"},
        ]
    )


class MockAnthropic(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/v1/messages") and "count_tokens" not in self.path:
            payload, kind = _reply(body), "text/event-stream"
        else:
            payload, kind = b'{"input_tokens": 1}', "application/json"
        self.send_response(200)
        self.send_header("content-type", kind)
        self.end_headers()
        self.wfile.write(payload)


def _setup() -> None:
    for d in (OWN, OTHER):
        d.mkdir(parents=True, exist_ok=True)
    (OTHER / "secret.txt").write_text("u2 secret")
    (DATA / "code_monet.db").write_text("auth db")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), MockAnthropic)
    threading.Thread(target=server.serve_forever, daemon=True).start()


async def _agent_turn() -> None:
    from claude_agent_sdk import ClaudeAgentOptions, query

    from code_monet.claude_runtime import claude_launch
    from code_monet.claude_sandbox import SPEC_ENV

    launch = claude_launch("u1", str(OWN))
    spec = json.loads(launch.env[SPEC_ENV])
    # Production shape (per-user home, not the developer's), pointed at the mock.
    home = DATA / "claude-home" / "u1"
    (home / "tmp").mkdir(parents=True, exist_ok=True)
    spec["env"] |= {
        "HOME": str(home),
        "TMPDIR": str(home / "tmp"),
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{PORT}",
        "ANTHROPIC_API_KEY": "mock-not-a-key",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    spec["write"] = [str(OWN), str(home), "/dev"]
    options = ClaudeAgentOptions(
        cli_path=launch.cli_path,
        env={SPEC_ENV: json.dumps(spec)},
        cwd=launch.cwd,
        allowed_tools=["Bash", "Read", "Grep"],
        permission_mode="acceptEdits",
        setting_sources=[],
        max_turns=len(TOOL_CALLS) + 2,
    )
    async for _ in query(prompt="probe", options=options):
        pass


async def _paint(source: str) -> Any:
    from code_monet.program_painting import run_painting_program
    from code_monet.types import DrawingStyleType
    from code_monet.workspace import WorkspaceState

    state = WorkspaceState(user_id="u1", user_dir=OWN)
    state._loaded = True
    state.canvas.width, state.canvas.height = 80, 60
    state.canvas.drawing_style = DrawingStyleType.PAINT
    state.studio_program.parent.mkdir(parents=True, exist_ok=True)
    state.studio_program.write_text(source)
    return await run_painting_program(state)


def main() -> int:
    from code_monet.program_painting import PaintFailure, PaintSuccess

    _setup()
    failures: list[str] = []

    asyncio.run(_agent_turn())
    bash, read, grep = (tool_results + ["", "", ""])[:3]
    print("agent Bash:\n" + bash)
    print("agent Read of another user:", read)
    print("agent Grep:", grep)
    failures += [line for line in bash.splitlines() if line.startswith("LEAK")]
    expected = {
        "ok:server-environ",
        "ok:env",
        "ok:other-user",
        "ok:db",
        "ok:signal-server",
        "ok:chmod",
        "ok:fchmod-runtime",
        "ok:shared-tmp",
        "ok:own-write",
        "ok:python",
    }
    failures += [f"missing {ok}" for ok in sorted(expected - set(bash.splitlines()))]
    if "EACCES" not in read:
        failures.append(f"Read of another user's file: {read!r}")
    if "own.txt" not in grep:
        failures.append(f"Grep in own workspace: {grep!r}")

    probe = asyncio.run(_paint(PAINT_PROBE))
    assert isinstance(probe, PaintFailure) and "PROBE " in probe.error, probe
    seen = json.loads(probe.error.split("PROBE ", 1)[1].splitlines()[0])
    print("paint probe:", seen)
    failures += [f"paint {k}" for k, v in seen.items() if v != "ok"]
    painted = asyncio.run(_paint(PAINTING))
    print("paint normal program:", type(painted).__name__)
    if not isinstance(painted, PaintSuccess):
        failures.append(f"normal painting failed: {painted}")

    from code_monet.tools.python_sandbox import run_python_code

    svg = asyncio.run(run_python_code(SVG_PROBE, 40, 30))
    seen = json.loads(svg["stdout"].split("PROBE ", 1)[1].splitlines()[0])
    print("generate_svg probe:", seen, "paths:", len(svg["paths"]))
    failures += [f"generate_svg {k}" for k, v in seen.items() if v != "ok"]
    if len(svg["paths"]) != 1:
        failures.append(f"generate_svg output broke: {svg['stderr'][-300:]}")

    if failures:
        print("FAILED:", *failures, sep="\n  ")
        return 1
    print("sandbox e2e: ok")
    return 0


if __name__ == "__main__":
    os.chdir("/")
    sys.exit(main())
