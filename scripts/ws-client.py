#!/usr/bin/env python3
"""
WebSocket client for orchestrating Code Monet from terminal.

Usage:
    uv run python scripts/ws-client.py watch              # Watch all events
    uv run python scripts/ws-client.py start [prompt]     # Start drawing
    uv run python scripts/ws-client.py pause              # Pause agent
    uv run python scripts/ws-client.py resume             # Resume agent
    uv run python scripts/ws-client.py nudge [message]    # Send nudge
    uv run python scripts/ws-client.py clear              # Clear canvas
    uv run python scripts/ws-client.py status             # Get status
    uv run python scripts/ws-client.py view [output.png]  # Save canvas image
    uv run python scripts/ws-client.py test "prompt" --strokes N  # E2E test
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime

import httpx
import websockets

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

# ANSI colors
CYAN = "\033[96m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def format_event(msg: dict) -> str:
    """Format a WebSocket event for display."""
    msg_type = msg.get("type", "unknown")

    if msg_type == "thinking":
        text = msg.get("thinking", "")[:100]
        if len(msg.get("thinking", "")) > 100:
            text += "..."
        return f"{CYAN}[{ts()}] thinking{RESET} {text}"

    elif msg_type == "text":
        text = msg.get("text", "")[:100]
        return f"{BLUE}[{ts()}] text{RESET} {text}"

    elif msg_type == "tool_use":
        name = msg.get("name", "unknown")
        status = msg.get("status", "")
        color = GREEN if status == "completed" else YELLOW
        return f"{color}[{ts()}] tool_use{RESET} {name} ({status})"

    elif msg_type == "paths":
        paths = msg.get("paths", [])
        return f"{MAGENTA}[{ts()}] paths{RESET} {len(paths)} paths received"

    elif msg_type == "status":
        status = msg.get("status", "")
        return f"{GREEN}[{ts()}] status{RESET} {status}"

    elif msg_type == "error":
        error = msg.get("error", str(msg))[:100]
        return f"{RED}[{ts()}] error{RESET} {error}"

    elif msg_type == "canvas_state":
        paths = msg.get("paths", [])
        return f"{DIM}[{ts()}] canvas_state{RESET} {len(paths)} paths"

    elif msg_type == "agent_state":
        status = msg.get("status", "")
        return f"{DIM}[{ts()}] agent_state{RESET} status={status}"

    else:
        preview = json.dumps(msg)[:80]
        return f"{DIM}[{ts()}] {msg_type}{RESET} {preview}"


async def get_token() -> str:
    """Get dev authentication token."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/auth/dev-token")
        if resp.status_code == 403:
            print(f"{RED}Error: Dev tokens only available in dev mode{RESET}")
            print("Set DEV_MODE=true on server")
            sys.exit(1)
        if resp.status_code != 200:
            print(f"{RED}Error: Failed to get token: {resp.status_code}{RESET}")
            sys.exit(1)
        return resp.json()["access_token"]


async def watch():
    """Watch all WebSocket events."""
    print(f"{GREEN}Connecting...{RESET}")
    token = await get_token()

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        print(f"{GREEN}Connected. Watching events (Ctrl+C to stop){RESET}\n")
        try:
            async for raw in ws:
                msg = json.loads(raw)
                print(format_event(msg))
        except KeyboardInterrupt:
            print(f"\n{DIM}Disconnected{RESET}")


async def send_and_watch(message: dict, watch_duration: int = 0):
    """Send a message and optionally watch for responses."""
    token = await get_token()

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        # Send the message
        await ws.send(json.dumps(message))
        print(f"{GREEN}Sent:{RESET} {json.dumps(message)}")

        if watch_duration > 0:
            print(f"\n{GREEN}Watching for {watch_duration}s (Ctrl+C to stop){RESET}\n")
            start = time.monotonic()
            try:
                while time.monotonic() - start < watch_duration:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg = json.loads(raw)
                        print(format_event(msg))
                    except TimeoutError:
                        continue
            except KeyboardInterrupt:
                print(f"\n{DIM}Stopped{RESET}")
        else:
            # Just get initial response
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                msg = json.loads(raw)
                print(format_event(msg))
            except TimeoutError:
                pass


async def fetch_and_animate_strokes(token: str) -> int:
    """Fetch pending strokes and simulate animation. Returns stroke count."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BASE_URL}/strokes/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            print(f"{RED}Failed to fetch strokes: {resp.status_code}{RESET}")
            return 0
        data = resp.json()
        strokes = data.get("strokes", [])
        if strokes:
            # Simulate animation time (100ms per stroke, max 2s)
            anim_time = min(len(strokes) * 0.1, 2.0)
            print(f"{MAGENTA}[{ts()}] animating{RESET} {len(strokes)} strokes ({anim_time:.1f}s)")
            await asyncio.sleep(anim_time)
        return len(strokes)


async def start(prompt: str | None = None, duration: int = 60, drawing_style: str | None = None):
    """Start drawing and watch."""
    token = await get_token()

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        # Send new_canvas with optional direction (prompt)
        new_canvas_msg = {"type": "new_canvas"}
        if prompt:
            new_canvas_msg["direction"] = prompt
        if drawing_style:
            new_canvas_msg["drawing_style"] = drawing_style
        await ws.send(json.dumps(new_canvas_msg))
        print(f"{GREEN}Sent:{RESET} {json.dumps(new_canvas_msg)}")

        # new_canvas auto-resumes, but send resume to be sure
        resume_msg = {"type": "resume"}
        await ws.send(json.dumps(resume_msg))
        print(f"{GREEN}Sent:{RESET} {json.dumps(resume_msg)}")

        print(f"\n{GREEN}Watching for {duration}s (Ctrl+C to stop){RESET}\n")
        start_time = time.monotonic()
        try:
            while time.monotonic() - start_time < duration:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    print(format_event(msg))

                    # When strokes are ready, fetch, animate, and signal done
                    if msg.get("type") == "agent_strokes_ready":
                        stroke_count = await fetch_and_animate_strokes(token)
                        if stroke_count > 0:
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "animation_done",
                                        "batch_id": msg.get("batch_id"),
                                    }
                                )
                            )
                            print(f"{GREEN}[{ts()}] Sent animation_done{RESET}")

                except TimeoutError:
                    continue
        except KeyboardInterrupt:
            print(f"\n{DIM}Stopped{RESET}")


async def pause():
    """Pause the agent."""
    await send_and_watch({"type": "pause"}, watch_duration=3)


async def resume():
    """Resume the agent."""
    await send_and_watch({"type": "resume"}, watch_duration=30)


async def nudge(message: str | None = None):
    """Send a nudge."""
    msg = {"type": "nudge"}
    if message:
        msg["text"] = message
    await send_and_watch(msg, watch_duration=30)


async def clear():
    """Clear the canvas."""
    await send_and_watch({"type": "clear"}, watch_duration=2)


async def status():
    """Get agent status."""
    token = await get_token()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/debug/agent",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            print(f"{RED}Failed to get status: {resp.status_code}{RESET}")
            return
        data = resp.json()
        print(f"{GREEN}Agent Status:{RESET}")
        print(f"  status: {data.get('status')}")
        print(f"  paused: {data.get('paused')}")
        print(f"  piece_count: {data.get('piece_count')}")
        print(f"  stroke_count: {data.get('stroke_count')}")
        print(f"  connected_clients: {data.get('connected_clients')}")


async def view(output_path: str = "canvas.png"):
    """Fetch and save the canvas image."""
    token = await get_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{BASE_URL}/canvas.png",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            print(f"{RED}Failed to fetch canvas: {resp.status_code}{RESET}")
            return
        with open(output_path, "wb") as f:
            f.write(resp.content)
        print(f"{GREEN}Saved canvas to:{RESET} {output_path}")


async def get_status_data(token: str | None = None) -> dict:
    """Get agent status data."""
    if token is None:
        token = await get_token()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/debug/agent",
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.json()


async def test(prompt: str, expected_strokes: int, timeout: int = 120):
    """Run an E2E drawing test."""
    token = await get_token()
    print(f"{CYAN}E2E Test:{RESET} {prompt}")
    print(f"  Expected strokes: {expected_strokes}")
    print(f"  Timeout: {timeout}s\n")

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        # Clear canvas first
        await ws.send(json.dumps({"type": "clear"}))
        print(f"{GREEN}[{ts()}] Cleared canvas{RESET}")

        # Start with prompt
        new_canvas_msg = {"type": "new_canvas", "direction": prompt}
        await ws.send(json.dumps(new_canvas_msg))
        print(f"{GREEN}[{ts()}] Started with prompt{RESET}")

        # Resume to start drawing
        await ws.send(json.dumps({"type": "resume"}))
        print(f"{GREEN}[{ts()}] Resumed agent{RESET}")

        # Watch until idle or timeout
        # We need to see the agent become non-idle first, then wait for it to go idle
        start_time = time.monotonic()
        seen_active = False

        while time.monotonic() - start_time < timeout:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                msg = json.loads(raw)

                # Track agent status changes
                if msg.get("type") == "agent_state":
                    agent_status = msg.get("status")
                    print(f"{DIM}[{ts()}] agent_state: {agent_status}{RESET}")

                    # Track when agent becomes active
                    if agent_status in ("thinking", "drawing", "running"):
                        seen_active = True

                    # Only consider done if we saw activity first
                    if agent_status == "idle" and seen_active:
                        print(f"{GREEN}[{ts()}] Agent finished{RESET}")
                        break

                # Handle stroke animation
                elif msg.get("type") == "agent_strokes_ready":
                    seen_active = True
                    stroke_count = await fetch_and_animate_strokes(token)
                    if stroke_count > 0:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "animation_done",
                                    "batch_id": msg.get("batch_id"),
                                }
                            )
                        )
                        print(f"{GREEN}[{ts()}] animation_done sent{RESET}")

                # Show tool use - indicates activity
                elif msg.get("type") == "tool_use":
                    seen_active = True
                    name = msg.get("name", "")
                    status = msg.get("status", "")
                    if status == "completed":
                        print(f"{YELLOW}[{ts()}] tool: {name}{RESET}")

                # Thinking indicates activity
                elif msg.get("type") == "thinking":
                    seen_active = True

            except TimeoutError:
                # Check status periodically (only if we've seen activity)
                if seen_active:
                    data = await get_status_data(token)
                    if data.get("status") == "idle":
                        print(f"{GREEN}[{ts()}] Agent idle{RESET}")
                        break
                continue

        # Wait a moment for final state to settle
        await asyncio.sleep(1)

    # Fetch final status
    data = await get_status_data(token)
    actual_strokes = data.get("stroke_count", 0)

    # Save canvas
    output_path = "canvas.png"
    await view(output_path)

    # Report results
    print(f"\n{CYAN}Results:{RESET}")
    print(f"  Expected strokes: {expected_strokes}")
    print(f"  Actual strokes: {actual_strokes}")
    print(f"  Canvas saved: {output_path}")

    if actual_strokes == expected_strokes:
        print(f"\n{GREEN}✓ PASS{RESET}")
        return True
    else:
        print(f"\n{RED}✗ FAIL{RESET} (expected {expected_strokes}, got {actual_strokes})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Code Monet WebSocket client")
    parser.add_argument(
        "command",
        choices=[
            "watch",
            "start",
            "pause",
            "resume",
            "nudge",
            "clear",
            "status",
            "view",
            "test",
        ],
    )
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=60,
        help="Watch duration for start command",
    )
    parser.add_argument("--strokes", "-s", type=int, help="Expected stroke count for test command")
    parser.add_argument("--timeout", "-t", type=int, default=120, help="Timeout for test command")
    parser.add_argument(
        "--style",
        choices=["plotter", "paint"],
        help="Drawing style for start command",
    )

    args = parser.parse_args()

    try:
        if args.command == "watch":
            asyncio.run(watch())
        elif args.command == "start":
            prompt = " ".join(args.args) if args.args else None
            asyncio.run(start(prompt, args.duration, args.style))
        elif args.command == "pause":
            asyncio.run(pause())
        elif args.command == "resume":
            asyncio.run(resume())
        elif args.command == "nudge":
            message = " ".join(args.args) if args.args else None
            asyncio.run(nudge(message))
        elif args.command == "clear":
            asyncio.run(clear())
        elif args.command == "status":
            asyncio.run(status())
        elif args.command == "view":
            output_path = args.args[0] if args.args else "canvas.png"
            asyncio.run(view(output_path))
        elif args.command == "test":
            if not args.args:
                print(f"{RED}Error: test command requires a prompt{RESET}")
                print('Usage: ws-client.py test "prompt" --strokes N')
                sys.exit(1)
            if args.strokes is None:
                print(f"{RED}Error: test command requires --strokes{RESET}")
                print('Usage: ws-client.py test "prompt" --strokes N')
                sys.exit(1)
            prompt = " ".join(args.args)
            success = asyncio.run(test(prompt, args.strokes, args.timeout))
            sys.exit(0 if success else 1)
    except httpx.ConnectError:
        print(f"{RED}Error: Cannot connect to server at {BASE_URL}{RESET}")
        print("Run: make dev-web")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{DIM}Interrupted{RESET}")


if __name__ == "__main__":
    main()
