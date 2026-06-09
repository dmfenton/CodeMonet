#!/usr/bin/env python3
"""Visual flow test: Time-lapse screenshot capture during agent execution.

Captures screenshots at regular intervals to verify rendering flow:
- Progressive text reveal (words appear 3 at a time)
- Strokes waiting until thinking animation completes
- Smooth transitions between states

Usage:
    uv run python scripts/visual-flow-test.py [prompt] [options]

Examples:
    uv run python scripts/visual-flow-test.py "draw a simple line"
    uv run python scripts/visual-flow-test.py "draw a landscape" --interval 0.5
    uv run python scripts/visual-flow-test.py "draw shapes" --expo-port 5173 --no-headless

Options:
    --interval N      Screenshot interval in seconds (default: 1.0)
    --timeout N       Max test duration in seconds (default: 120)
    --output DIR      Output directory (default: screenshots/flow-{timestamp}/)
    --expo-port N     Expo port (default: 8081 for mobile, 5173 for web)
    --renderer TYPE   Renderer to use: svg or freehand (default: svg)
    --no-headless     Show browser window for debugging
    --no-clear        Skip clearing canvas before test
    --no-teardown     Skip killing stale processes and clearing state
    --no-video        Skip creating and opening timelapse video
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import websockets

# Constants
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"
WS_MAX_SIZE = 16 * 1024 * 1024
DEFAULT_EXPO_PORT = 8081
DEFAULT_VIEWPORT = (390, 844)  # iPhone 14 Pro

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
    """Return current timestamp string."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


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


async def full_teardown(token: str) -> None:
    """Clean slate before test - kill stale processes and clear agent state."""
    import os
    my_pid = os.getpid()
    print(f"{CYAN}[TEARDOWN] Killing stale test processes (excluding pid {my_pid})...{RESET}")
    # Find other visual-flow-test processes and kill them (not ourselves)
    result = subprocess.run(
        ["pgrep", "-f", "visual-flow-test"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        for pid_str in result.stdout.strip().split("\n"):
            if pid_str:
                pid = int(pid_str)
                if pid != my_pid:
                    try:
                        os.kill(pid, 9)
                        print(f"{CYAN}[TEARDOWN] Killed stale process {pid}{RESET}")
                    except ProcessLookupError:
                        pass

    print(f"{CYAN}[TEARDOWN] Clearing agent state...{RESET}")
    try:
        async with websockets.connect(f"{WS_URL}?token={token}", max_size=WS_MAX_SIZE) as ws:
            # Wait for init
            init_timeout = 5.0
            start = time.monotonic()
            while time.monotonic() - start < init_timeout:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    if msg.get("type") == "init":
                        print(f"{GREEN}[TEARDOWN] WebSocket connected{RESET}")
                        break
                except TimeoutError:
                    continue

            # Pause and clear
            await ws.send(json.dumps({"type": "pause"}))
            await asyncio.sleep(0.3)
            await ws.send(json.dumps({"type": "clear"}))
            await asyncio.sleep(0.5)
            print(f"{GREEN}[TEARDOWN] Agent paused and canvas cleared{RESET}")
    except Exception as e:
        print(f"{YELLOW}[TEARDOWN] Warning: {e}{RESET}")


class VisualFlowTest:
    """Orchestrates visual flow testing with WebSocket monitoring and screenshots."""

    def __init__(
        self,
        prompt: str,
        interval: float = 1.0,
        timeout: int = 120,
        output_dir: Path | None = None,
        expo_port: int = DEFAULT_EXPO_PORT,
        headless: bool = True,
        clear_canvas: bool = True,
        do_teardown: bool = True,
        create_video: bool = True,
        renderer: str = "svg",
    ):
        self.prompt = prompt
        self.interval = interval
        self.timeout = timeout
        self.expo_port = expo_port
        self.headless = headless
        self.clear_canvas = clear_canvas
        self.do_teardown = do_teardown
        self.create_video = create_video
        self.renderer = renderer

        # Output directory
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.output_dir = Path("screenshots") / f"flow-{timestamp}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State tracking
        self.token: str | None = None
        self.events: list[dict] = []
        self.screenshot_count = 0
        self.start_time: float = 0
        self.agent_active = False
        self.agent_idle = False
        self.stroke_count = 0
        self.thinking_count = 0
        self.current_state = "idle"

        # WebSocket readiness
        self.init_received = False
        self.ws_monitor_task: asyncio.Task | None = None

        # Playwright objects (set in run)
        self.browser = None
        self.page = None

    def log(self, msg: str, color: str = RESET) -> None:
        """Log a message with timestamp."""
        print(f"{color}[{ts()}] {msg}{RESET}")

    def record_event(self, event_type: str, data: dict | None = None) -> None:
        """Record an event for the log."""
        event = {
            "timestamp": time.monotonic() - self.start_time,
            "type": event_type,
            "wall_time": datetime.now().isoformat(),
        }
        if data:
            event["data"] = data
        self.events.append(event)

    def transition_state(self, new_state: str) -> None:
        """Log state transition."""
        if new_state != self.current_state:
            self.log(f"[STATE] {self.current_state} → {new_state}", YELLOW)
            self.record_event("state_transition", {"from": self.current_state, "to": new_state})
            self.current_state = new_state

    async def setup_browser(self) -> None:
        """Launch Playwright browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print(f"{RED}Error: Playwright not installed{RESET}")
            print("Run: cd server && uv sync --extra dev && uv run playwright install chromium")
            sys.exit(1)

        self.log("Launching browser...", CYAN)
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)

        context = await self.browser.new_context(
            viewport={"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            device_scale_factor=2,
        )

        self.page = await context.new_page()

        # Log console messages for debugging
        self.page.on("console", lambda msg: self.log(f"CONSOLE: {msg.text}", DIM))
        self.page.on("pageerror", lambda err: self.log(f"PAGE ERROR: {err}", RED))

        # Navigate to blank page first to set up localStorage before app loads
        # This prevents creating multiple WebSocket connections
        url = f"http://localhost:{self.expo_port}/"
        self.log(f"Setting up auth for {url}...", CYAN)

        # Navigate to about:blank first (same origin not required for localStorage)
        # Actually, we need to be on the same origin to set localStorage
        # So we navigate to the app URL but intercept before it fully loads
        try:
            # Quick navigate to set origin for localStorage
            await self.page.goto(url, wait_until="commit", timeout=10000)
        except Exception as e:
            print(f"{RED}Error: Failed to load {url}: {e}{RESET}")
            print(f"Is Expo running? Port: {self.expo_port}")
            sys.exit(1)

        # Inject auth token into localStorage BEFORE app fully initializes
        token_js = json.dumps(self.token)
        if self.expo_port == 5173:
            await self.page.evaluate(f"""
                localStorage.setItem('auth_access_token', {token_js});
                localStorage.setItem('auth_refresh_token', {token_js});
            """)
        else:
            await self.page.evaluate(f"""
                localStorage.setItem('access_token', {token_js});
                localStorage.setItem('refresh_token', {token_js});
            """)
        self.log("Injected auth token", GREEN)

        # Now navigate properly (or wait for networkidle)
        if self.expo_port == 5173:
            await self.page.goto(f"http://localhost:{self.expo_port}/studio", wait_until="networkidle")
            self.log("Navigated to /studio", GREEN)
        else:
            # Wait for the page to fully load with auth in place
            await self.page.wait_for_load_state("networkidle")
        self.log("Browser ready", GREEN)

        # Wait for WebSocket to connect
        await asyncio.sleep(2)

    async def take_screenshot(self) -> str:
        """Take a screenshot and return the filename."""
        self.screenshot_count += 1
        elapsed_ms = int((time.monotonic() - self.start_time) * 1000)
        filename = f"{self.screenshot_count:03d}-{elapsed_ms:05d}ms.png"
        filepath = self.output_dir / filename

        await self.page.screenshot(path=str(filepath), full_page=False)
        self.record_event("screenshot", {"filename": filename, "elapsed_ms": elapsed_ms})
        self.log(f"Screenshot: {filename}", MAGENTA)
        return filename

    async def screenshot_loop(self, stop_event: asyncio.Event) -> None:
        """Take screenshots at regular intervals until stopped."""
        while not stop_event.is_set():
            await self.take_screenshot()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval)
                break  # stop_event was set
            except TimeoutError:
                pass  # Continue taking screenshots

    async def enter_studio_via_ui(self) -> None:
        """Enter studio mode by typing prompt and submitting via UI."""
        # Different flow for web app (port 5173) vs mobile app
        if self.expo_port == 5173:
            await self._enter_studio_web()
        else:
            await self._enter_studio_mobile()

    async def _enter_studio_web(self) -> None:
        """Web app flow: click Start button, enter direction in modal."""
        self.log("Waiting for Start button...", CYAN)
        start_btn_selector = "button.start-btn"

        try:
            await self.page.wait_for_selector(start_btn_selector, timeout=10000)
        except Exception:
            self.log("Start button not found - agent may already be running", YELLOW)
            return

        # Click Start button to open modal
        await self.page.click(start_btn_selector)
        await asyncio.sleep(0.3)

        # Type in modal input
        modal_input_selector = ".modal input[type='text']"
        try:
            await self.page.wait_for_selector(modal_input_selector, timeout=5000)
            if not await self.wait_for_input_enabled(modal_input_selector, timeout=10.0):
                self.log("[UI] Modal input disabled (WS not connected?)", YELLOW)
            await self.page.fill(modal_input_selector, self.prompt)
            self.record_event("prompt_entered", {"prompt": self.prompt})

            # Click modal Start button
            await self.page.click(".modal button.primary")
            self.log("Started agent with direction", GREEN)
            self.record_event("prompt_submitted")
        except Exception as e:
            self.log(f"Modal interaction failed: {e}", YELLOW)

        await asyncio.sleep(1)

    async def _enter_studio_mobile(self) -> None:
        """Mobile app flow: type in home panel input and submit."""
        self.log("Waiting for home panel...", CYAN)
        input_selector = '[data-testid="home-prompt-input"]'
        submit_selector = '[data-testid="home-prompt-submit"]'

        try:
            await self.page.wait_for_selector(input_selector, timeout=10000)
        except Exception:
            self.log("Home panel input not found, trying to continue anyway", YELLOW)
            return

        if not await self.wait_for_input_enabled(input_selector, timeout=10.0):
            self.log("[UI] Prompt input disabled (WS not connected?)", YELLOW)

        # Select renderer if specified (click the button)
        renderer_btn = f'[data-testid="renderer-{self.renderer}-button"]'
        try:
            btn = await self.page.wait_for_selector(renderer_btn, timeout=3000)
            if btn:
                await btn.click()
                self.log(f"[UI] Selected renderer: {self.renderer}", GREEN)
                self.record_event("renderer_selected", {"renderer": self.renderer})
                await asyncio.sleep(0.2)
        except Exception:
            self.log(f"[UI] Renderer button not found: {renderer_btn}", YELLOW)

        # Type the prompt
        await self.page.fill(input_selector, self.prompt)
        self.record_event("prompt_entered", {"prompt": self.prompt})

        # Click submit
        await self.page.click(submit_selector)
        self.log("Submitted prompt", GREEN)
        self.record_event("prompt_submitted")

        # Wait for studio view to appear (canvas)
        await asyncio.sleep(1)

    async def websocket_monitor(self, stop_event: asyncio.Event) -> None:
        """Monitor WebSocket events and track state."""
        async with websockets.connect(f"{WS_URL}?token={self.token}", max_size=WS_MAX_SIZE) as ws:
            self.log("[WS] Connected", GREEN)

            # Monitor events
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "unknown")

                    # Record all events
                    self.record_event(f"ws:{msg_type}", msg)

                    # Track init for readiness
                    if msg_type == "init":
                        self.init_received = True
                        self.log("[WS] Init received - ready", GREEN)
                        continue

                    # Track state transitions
                    if msg_type == "agent_state":
                        status = msg.get("status", "")
                        if status in ("thinking", "running"):
                            self.transition_state("thinking")
                            self.agent_active = True
                        elif status == "drawing":
                            self.transition_state("drawing")
                            self.agent_active = True
                        elif status == "idle" and self.agent_active:
                            self.transition_state("idle")
                            self.log("[WS] Agent finished (idle)", GREEN)
                            self.agent_idle = True
                            stop_event.set()

                    elif msg_type == "thinking_delta":
                        text_len = len(msg.get("text", ""))
                        self.log(f"[WS] thinking_delta (len={text_len})", DIM)
                        self.thinking_count += 1
                        self.transition_state("thinking")
                        self.agent_active = True

                    elif msg_type == "thinking":
                        text = msg.get("thinking", "")[:60]
                        self.log(f"[WS] thinking: {text}...", CYAN)
                        self.thinking_count += 1
                        self.transition_state("thinking")
                        self.agent_active = True

                    elif msg_type == "tool_use":
                        name = msg.get("name", "")
                        status = msg.get("status", "")
                        self.log(f"[WS] tool_use: {name} ({status})", BLUE)
                        self.agent_active = True

                    elif msg_type == "code_execution":
                        name = msg.get("name", "")
                        status = msg.get("status", "")
                        self.log(f"[WS] code_execution: {name} {status}", BLUE)
                        self.agent_active = True

                    elif msg_type == "agent_strokes_ready":
                        count = msg.get("count", 0)
                        self.stroke_count += count
                        self.log(f"[WS] agent_strokes_ready: count={count}", MAGENTA)
                        self.transition_state("drawing")
                        self.agent_active = True

                    elif msg_type == "animation_done":
                        self.log("[WS] animation_done", MAGENTA)

                    elif msg_type == "error":
                        error = msg.get("error", str(msg))
                        self.log(f"[WS] Error: {error}", RED)

                except TimeoutError:
                    # Check if we've exceeded timeout
                    if time.monotonic() - self.start_time > self.timeout:
                        self.log("Timeout reached", YELLOW)
                        stop_event.set()
                except websockets.exceptions.ConnectionClosed:
                    self.log("[WS] Connection closed", RED)
                    stop_event.set()

    async def wait_for_ws_ready(self, timeout: float = 10.0) -> bool:
        """Wait for WebSocket init message."""
        start = time.monotonic()
        while not self.init_received and time.monotonic() - start < timeout:
            await asyncio.sleep(0.1)
        return self.init_received

    async def wait_for_input_enabled(self, selector: str, timeout: float = 10.0) -> bool:
        """Wait for an input element to become enabled."""
        if not self.page:
            return False
        try:
            await self.page.wait_for_function(
                """
                (sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                    return !disabled;
                }
                """,
                selector,
                timeout=timeout * 1000,
            )
            return True
        except Exception:
            return False

    def write_summary(self) -> None:
        """Write test summary to file."""
        duration = time.monotonic() - self.start_time

        # Save events log
        events_path = self.output_dir / "events.json"
        with open(events_path, "w") as f:
            json.dump(self.events, f, indent=2)

        # Write summary
        summary = [
            "Visual Flow Test Summary",
            "========================",
            "",
            f"Prompt: {self.prompt}",
            f"Renderer: {self.renderer}",
            f"Duration: {duration:.1f}s",
            f"Screenshots: {self.screenshot_count}",
            f"Strokes: {self.stroke_count}",
            f"Thinking messages: {self.thinking_count}",
            f"Interval: {self.interval}s",
            f"Agent finished: {'Yes' if self.agent_idle else 'No (timeout)'}",
            "",
            f"Output directory: {self.output_dir}",
            "Events log: events.json",
            "",
            "To create time-lapse:",
            f"  ffmpeg -framerate 4 -pattern_type glob -i '{self.output_dir}/*.png' -vf scale=600:-1 -c:v libx264 -pix_fmt yuv420p timelapse.mp4",
        ]

        summary_path = self.output_dir / "summary.txt"
        with open(summary_path, "w") as f:
            f.write("\n".join(summary))

        # Print summary
        print(f"\n{GREEN}{'=' * 50}{RESET}")
        for line in summary:
            print(line)
        print(f"{GREEN}{'=' * 50}{RESET}")

    def create_and_open_video(self) -> Path | None:
        """Create timelapse video and open in default viewer."""
        # Check for ffmpeg
        if not shutil.which("ffmpeg"):
            self.log("ffmpeg not found, skipping video creation", YELLOW)
            return None

        output_video = self.output_dir / "timelapse.mp4"
        self.log("[VIDEO] Creating timelapse...", CYAN)

        # Build ffmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-framerate", "4",
            "-pattern_type", "glob",
            "-i", f"{self.output_dir}/*.png",
            "-vf", "scale=600:-1",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output_video),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.log(f"[VIDEO] ffmpeg failed: {result.stderr[:200]}", RED)
            return None

        self.log(f"[VIDEO] Created: {output_video}", GREEN)

        # Open video on macOS
        if sys.platform == "darwin":
            subprocess.run(["open", str(output_video)])
            self.log("[VIDEO] Opened in default player", GREEN)

        return output_video

    async def run(self) -> bool:
        """Run the visual flow test. Returns True if agent completed."""
        print(f"\n{CYAN}Visual Flow Test{RESET}")
        print(f"Prompt: {self.prompt}")
        print(f"Interval: {self.interval}s, Timeout: {self.timeout}s")
        print(f"Output: {self.output_dir}\n")

        # Get auth token
        self.log("Getting auth token...", CYAN)
        self.token = await get_token()

        # Full teardown before test
        if self.do_teardown:
            await full_teardown(self.token)

        # Setup browser
        await self.setup_browser()

        # Start tracking
        self.start_time = time.monotonic()
        stop_event = asyncio.Event()

        # Start WebSocket monitor in background
        self.ws_monitor_task = asyncio.create_task(self.websocket_monitor(stop_event))

        # Wait for WebSocket to be ready
        self.log("Waiting for WebSocket init...", CYAN)
        if not await self.wait_for_ws_ready(timeout=10.0):
            self.log("WebSocket init timeout - continuing anyway", YELLOW)

        try:
            # Take initial screenshot (home panel)
            await self.take_screenshot()

            # Enter studio via UI (type prompt and submit)
            self.log(f"[UI] Entering prompt: \"{self.prompt}\"", CYAN)
            await self.enter_studio_via_ui()
            self.log("[UI] Submitted", GREEN)

            # Take screenshot after entering studio
            await self.take_screenshot()

            # Take screenshots at interval until stopped or timeout
            end_time = self.start_time + self.timeout
            while not stop_event.is_set() and time.monotonic() < end_time:
                await asyncio.sleep(self.interval)
                await self.take_screenshot()

            if not stop_event.is_set():
                self.log("Timeout reached", YELLOW)

        finally:
            # Stop WebSocket monitor
            stop_event.set()
            if self.ws_monitor_task:
                try:
                    await asyncio.wait_for(self.ws_monitor_task, timeout=2.0)
                except TimeoutError:
                    self.ws_monitor_task.cancel()

            # Cleanup browser
            if self.browser:
                await self.browser.close()
            if hasattr(self, "playwright"):
                await self.playwright.stop()

        # Log completion stats
        self.log(f"[COMPLETE] Strokes: {self.stroke_count}, Thinking: {self.thinking_count}, Screenshots: {self.screenshot_count}", GREEN)

        # Write summary
        self.write_summary()

        # Create and open video
        if self.create_video and self.screenshot_count > 0:
            self.create_and_open_video()

        return self.agent_idle


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Visual flow test: Time-lapse screenshot capture during agent execution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python scripts/visual-flow-test.py "draw a simple line"
  uv run python scripts/visual-flow-test.py "draw shapes" --interval 0.5
  uv run python scripts/visual-flow-test.py "draw a cat" --expo-port 5173 --no-headless

Prerequisites:
  - Dev servers running: make dev (or make dev-web for port 5173)
  - Playwright: cd server && uv sync --extra dev && uv run playwright install chromium
        """,
    )

    parser.add_argument(
        "prompt",
        nargs="?",
        default="draw a simple shape",
        help="Prompt to send to the agent",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Screenshot interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Max test duration in seconds (default: 120)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory (default: screenshots/flow-{timestamp}/)",
    )
    parser.add_argument(
        "--expo-port",
        type=int,
        default=DEFAULT_EXPO_PORT,
        help=f"Expo port (default: {DEFAULT_EXPO_PORT})",
    )
    parser.add_argument(
        "--renderer",
        type=str,
        choices=["svg", "freehand"],
        default="svg",
        help="Renderer to use: svg or freehand (default: svg)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show browser window for debugging",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Skip clearing canvas before test",
    )
    parser.add_argument(
        "--no-teardown",
        action="store_true",
        help="Skip killing stale processes and clearing state",
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Skip creating and opening timelapse video",
    )

    args = parser.parse_args()

    # Validate
    if args.interval <= 0:
        print(f"{RED}Error: --interval must be positive{RESET}")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else None

    test = VisualFlowTest(
        prompt=args.prompt,
        interval=args.interval,
        timeout=args.timeout,
        output_dir=output_dir,
        expo_port=args.expo_port,
        headless=not args.no_headless,
        clear_canvas=not args.no_clear,
        do_teardown=not args.no_teardown,
        create_video=not args.no_video,
        renderer=args.renderer,
    )

    try:
        success = asyncio.run(test.run())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{DIM}Interrupted{RESET}")
        sys.exit(1)
    except httpx.ConnectError:
        print(f"{RED}Error: Cannot connect to server at {BASE_URL}{RESET}")
        print("Run: make dev")
        sys.exit(1)


if __name__ == "__main__":
    main()
