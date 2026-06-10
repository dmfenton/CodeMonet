#!/usr/bin/env python3
"""Visual flow test: observe the agent painting end-to-end and produce
artifacts that are actually judgeable.

Captures:
- Interval screenshots (timelapse) PLUS event-triggered screenshots at the
  moments that matter (state changes, stroke batches, critique results)
- Canvas-only crops per stroke batch and a final settled frame
- A client/server parity image (stamping.ts canvas vs painting.py render)
- report.md: event timeline with thinking text, tool calls, and critique
  verdicts aligned to the screenshots
- contact-sheet.png: one-glance grid of the whole run
- events.json (compacted) and timelapse.mp4

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
    --expo-port N     App port (8081 Expo mobile, 5173 Vite web; default: 8081)
    --viewport WxH    Viewport (default: 390x844 mobile, 1280x900 web)
    --renderer TYPE   Mobile renderer to select: svg or freehand (default: svg)
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
from io import BytesIO
from pathlib import Path

import httpx
import websockets

# Constants
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"
WS_MAX_SIZE = 16 * 1024 * 1024
DEFAULT_EXPO_PORT = 8081
MOBILE_VIEWPORT = (390, 844)  # iPhone 14 Pro
WEB_VIEWPORT = (1280, 900)  # Desktop studio layout
CANVAS_SELECTOR = '[data-testid="canvas-view"]'
SETTLE_SECONDS = 2.5  # let reveal/stroke animations finish before final frames

# Message types whose payloads are too bulky to keep verbatim in events.json
BULKY_TYPES = {"canvas_state", "paths", "init"}

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


async def full_teardown(token: str, clear_canvas: bool) -> None:
    """Clean slate before test - kill stale processes and clear agent state."""
    import os

    my_pid = os.getpid()
    print(f"{CYAN}[TEARDOWN] Killing stale test processes (excluding pid {my_pid})...{RESET}")
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

    print(f"{CYAN}[TEARDOWN] Pausing agent...{RESET}")
    try:
        async with websockets.connect(f"{WS_URL}?token={token}", max_size=WS_MAX_SIZE) as ws:
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

            await ws.send(json.dumps({"type": "pause"}))
            await asyncio.sleep(0.3)
            if clear_canvas:
                await ws.send(json.dumps({"type": "clear"}))
                await asyncio.sleep(0.5)
                print(f"{GREEN}[TEARDOWN] Agent paused and canvas cleared{RESET}")
            else:
                print(f"{GREEN}[TEARDOWN] Agent paused (canvas kept){RESET}")
    except Exception as e:
        print(f"{YELLOW}[TEARDOWN] Warning: {e}{RESET}")


def extract_critique_summary(stdout: str) -> str:
    """Pull the verdict/gate/findings lines out of critique_canvas output."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    verdict = next((line for line in lines if line.startswith("VERDICT:")), "")
    gate = next((line for line in lines if line.startswith("FINISH GATE:")), "")
    repair = next((line for line in lines if line.startswith("STRUCTURAL REPAIR")), "")
    findings = [line for line in lines if line.startswith("- ")][:4]
    parts = [part for part in [verdict, gate, repair, *findings] if part]
    return " | ".join(parts)


class VisualFlowTest:
    """Orchestrates visual flow testing with WebSocket monitoring and screenshots."""

    def __init__(
        self,
        prompt: str,
        interval: float = 1.0,
        timeout: int = 120,
        output_dir: Path | None = None,
        expo_port: int = DEFAULT_EXPO_PORT,
        viewport: tuple[int, int] | None = None,
        headless: bool = True,
        clear_canvas: bool = True,
        do_teardown: bool = True,
        create_video: bool = True,
        renderer: str = "svg",
        web: bool | None = None,
    ):
        self.prompt = prompt
        self.interval = interval
        self.timeout = timeout
        self.expo_port = expo_port
        # Vite web app vs Expo mobile app (different auth keys, routes, UI)
        self.is_web = web if web is not None else (expo_port == 5173)
        self.viewport = viewport or (WEB_VIEWPORT if self.is_web else MOBILE_VIEWPORT)
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
        self.canvas_capture_count = 0
        self.start_time: float = 0
        self.agent_active = False
        self.agent_idle = False
        self.stroke_count = 0
        self.batch_count = 0
        self.thinking_count = 0
        self.thinking_chars = 0
        self.critiques: list[str] = []
        self.current_state = "idle"
        self.parity_diff: float | None = None
        self.client_state: dict | None = None

        # WebSocket readiness
        self.init_received = False
        self.ws_monitor_task: asyncio.Task | None = None
        self._pending_captures: set[asyncio.Task] = set()
        self._shot_lock = asyncio.Lock()

        # Playwright objects (set in run)
        self.browser = None
        self.page = None

    def log(self, msg: str, color: str = RESET) -> None:
        """Log a message with timestamp."""
        print(f"{color}[{ts()}] {msg}{RESET}")

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.start_time) * 1000)

    def _compact_msg(self, msg: dict) -> dict:
        """Trim bulky payloads so events.json stays readable."""
        msg_type = msg.get("type")
        if msg_type in BULKY_TYPES:
            out = {"type": msg_type}
            if isinstance(msg.get("paths"), list):
                out["path_count"] = len(msg["paths"])
            return out
        if msg_type == "code_execution":
            out = dict(msg)
            for key in ("stdout", "stderr"):
                value = out.get(key)
                if isinstance(value, str) and len(value) > 2000:
                    out[key] = value[:2000] + "…"
            tool_input = out.get("tool_input")
            if isinstance(tool_input, dict):
                code = tool_input.get("code")
                if isinstance(code, str) and len(code) > 1500:
                    out["tool_input"] = {**tool_input, "code": code[:1500] + "…"}
            return out
        return msg

    def record_event(self, event_type: str, data: dict | None = None) -> None:
        """Record an event for the log."""
        event = {
            "timestamp": time.monotonic() - self.start_time,
            "type": event_type,
            "wall_time": datetime.now().isoformat(),
        }
        if data:
            event["data"] = self._compact_msg(data)
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

        self.log(f"Launching browser ({self.viewport[0]}x{self.viewport[1]})...", CYAN)
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)

        context = await self.browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            device_scale_factor=2,
        )

        self.page = await context.new_page()

        # Log console messages for debugging
        self.page.on("console", lambda msg: self.log(f"CONSOLE: {msg.text}", DIM))
        self.page.on("pageerror", lambda err: self.log(f"PAGE ERROR: {err}", RED))

        url = f"http://localhost:{self.expo_port}/"
        self.log(f"Setting up auth for {url}...", CYAN)

        # Navigate to set origin so localStorage can be written pre-init
        try:
            await self.page.goto(url, wait_until="commit", timeout=10000)
        except Exception as e:
            print(f"{RED}Error: Failed to load {url}: {e}{RESET}")
            print(f"Is the app running? Port: {self.expo_port}")
            sys.exit(1)

        # Inject auth token into localStorage BEFORE app fully initializes
        token_js = json.dumps(self.token)
        if self.is_web:
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

        if self.is_web:
            await self.page.goto(
                f"http://localhost:{self.expo_port}/studio", wait_until="networkidle"
            )
            self.log("Navigated to /studio", GREEN)
        else:
            await self.page.wait_for_load_state("networkidle")
        self.log("Browser ready", GREEN)

        # Wait for WebSocket to connect
        await asyncio.sleep(2)

    async def take_screenshot(self, label: str | None = None) -> str | None:
        """Take a full-viewport screenshot. Returns the filename."""
        if not self.page:
            return None
        async with self._shot_lock:
            self.screenshot_count += 1
            elapsed = self.elapsed_ms()
            suffix = f"-{label}" if label else ""
            filename = f"{self.screenshot_count:03d}-{elapsed:06d}ms{suffix}.png"
            filepath = self.output_dir / filename
            try:
                await self.page.screenshot(path=str(filepath), full_page=False)
            except Exception as e:
                self.log(f"Screenshot failed: {e}", RED)
                return None
        self.record_event("screenshot", {"filename": filename, "elapsed_ms": elapsed})
        self.log(f"Screenshot: {filename}", MAGENTA)
        return filename

    async def capture_canvas(self, tag: str) -> str | None:
        """Screenshot just the canvas element (what the painting looks like)."""
        if not self.page:
            return None
        async with self._shot_lock:
            self.canvas_capture_count += 1
            elapsed = self.elapsed_ms()
            filename = f"canvas-{self.canvas_capture_count:03d}-{elapsed:06d}ms-{tag}.png"
            filepath = self.output_dir / filename
            try:
                await self.page.locator(CANVAS_SELECTOR).screenshot(
                    path=str(filepath), timeout=5000
                )
            except Exception as e:
                self.log(f"Canvas capture failed ({tag}): {e}", YELLOW)
                return None
        self.record_event("canvas_capture", {"filename": filename, "tag": tag})
        self.log(f"Canvas capture: {filename}", MAGENTA)
        return filename

    async def sample_client_state(self) -> dict | None:
        """Read the web app's dev-state hook (painted strokes, queue depth)."""
        if not self.page:
            return None
        try:
            state = await self.page.evaluate("window.__CM_DEV_STATE__ || null")
        except Exception:
            return None
        if state:
            self.client_state = state
            self.record_event("client_state", state)
        return state

    def _schedule_canvas_capture(self, delay: float, tag: str) -> None:
        """Capture the canvas after a delay (e.g. mid/post stroke animation)."""

        async def delayed() -> None:
            await asyncio.sleep(delay)
            await self.capture_canvas(tag)

        task = asyncio.create_task(delayed())
        self._pending_captures.add(task)
        task.add_done_callback(self._pending_captures.discard)

    async def enter_studio_via_ui(self) -> None:
        """Enter studio mode by typing prompt and submitting via UI."""
        if self.is_web:
            await self._enter_studio_web()
        else:
            await self._enter_studio_mobile()

    async def _enter_studio_web(self) -> None:
        """Web app flow: click Start button, enter direction in modal."""
        self.log("Waiting for Start button...", CYAN)
        start_btn_selector = '[data-testid="start-button"]'

        try:
            await self.page.wait_for_selector(start_btn_selector, timeout=10000)
        except Exception:
            self.log("Start button not found - agent may already be running", YELLOW)
            return

        await self.page.click(start_btn_selector)
        await asyncio.sleep(0.3)

        modal_input_selector = '[data-testid="start-modal-input"]'
        try:
            await self.page.wait_for_selector(modal_input_selector, timeout=5000)
            if not await self.wait_for_input_enabled(modal_input_selector, timeout=10.0):
                self.log("[UI] Modal input disabled (WS not connected?)", YELLOW)
            await self.page.fill(modal_input_selector, self.prompt)
            self.record_event("prompt_entered", {"prompt": self.prompt})

            await self.page.click('[data-testid="start-modal-submit"]')
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

        await self.page.fill(input_selector, self.prompt)
        self.record_event("prompt_entered", {"prompt": self.prompt})

        await self.page.click(submit_selector)
        self.log("Submitted prompt", GREEN)
        self.record_event("prompt_submitted")

        await asyncio.sleep(1)

    async def websocket_monitor(self, stop_event: asyncio.Event) -> None:
        """Monitor WebSocket events, track state, and trigger event screenshots."""
        async with websockets.connect(f"{WS_URL}?token={self.token}", max_size=WS_MAX_SIZE) as ws:
            self.log("[WS] Connected", GREEN)

            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "unknown")

                    self.record_event(f"ws:{msg_type}", msg)

                    if msg_type == "init":
                        self.init_received = True
                        self.log("[WS] Init received - ready", GREEN)
                        continue

                    if msg_type == "agent_state":
                        status = msg.get("status", "")
                        if status in ("thinking", "running"):
                            if self.current_state != "thinking":
                                self.transition_state("thinking")
                                await self.take_screenshot("state-thinking")
                            self.agent_active = True
                        elif status == "drawing":
                            if self.current_state != "drawing":
                                self.transition_state("drawing")
                                await self.take_screenshot("state-drawing")
                            self.agent_active = True
                        elif status == "idle" and self.agent_active:
                            self.transition_state("idle")
                            self.log("[WS] Agent finished (idle)", GREEN)
                            self.agent_idle = True
                            stop_event.set()

                    elif msg_type == "thinking_delta":
                        text = msg.get("text", "")
                        self.thinking_count += 1
                        self.thinking_chars += len(text)
                        self.transition_state("thinking")
                        self.agent_active = True

                    elif msg_type == "thinking":
                        text = msg.get("thinking", "")
                        self.thinking_count += 1
                        self.thinking_chars += len(text)
                        self.log(f"[WS] thinking: {text[:100]}...", CYAN)
                        self.transition_state("thinking")
                        self.agent_active = True

                    elif msg_type == "tool_use":
                        name = msg.get("name", "")
                        status = msg.get("status", "")
                        self.log(f"[WS] tool_use: {name} ({status})", BLUE)
                        self.agent_active = True

                    elif msg_type == "code_execution":
                        tool = msg.get("tool_name") or msg.get("name") or "unknown"
                        status = msg.get("status", "")
                        self.agent_active = True
                        if status == "completed" and tool == "critique_canvas":
                            summary = extract_critique_summary(msg.get("stdout") or "")
                            if summary:
                                self.critiques.append(summary)
                                self.log(f"[WS] critique: {summary[:300]}", BLUE)
                            await self.take_screenshot("critique")
                        else:
                            self.log(f"[WS] code_execution: {tool} {status}", BLUE)

                    elif msg_type == "agent_strokes_ready":
                        count = msg.get("count", 0)
                        self.stroke_count += count
                        self.batch_count += 1
                        self.log(f"[WS] agent_strokes_ready: count={count}", MAGENTA)
                        self.transition_state("drawing")
                        self.agent_active = True
                        await self.take_screenshot(f"strokes-batch{self.batch_count}")
                        # Catch the painting mid/post animation for this batch
                        self._schedule_canvas_capture(2.0, f"batch{self.batch_count}")

                    elif msg_type == "animation_done":
                        self.log("[WS] animation_done", MAGENTA)

                    elif msg_type == "error":
                        error = msg.get("error", str(msg))
                        self.log(f"[WS] Error: {error}", RED)
                        await self.take_screenshot("error")

                except TimeoutError:
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

    async def finalize_captures(self) -> None:
        """After the run: settled final frames and client/server parity image."""
        self.log(f"Settling {SETTLE_SECONDS}s before final frames...", CYAN)
        await asyncio.sleep(SETTLE_SECONDS)

        await self.sample_client_state()
        await self.take_screenshot("final")

        client_png_path = self.output_dir / "final-canvas.png"
        try:
            await self.page.locator(CANVAS_SELECTOR).screenshot(
                path=str(client_png_path), timeout=5000
            )
            self.log(f"Final canvas: {client_png_path.name}", MAGENTA)
        except Exception as e:
            self.log(f"Final canvas capture failed: {e}", YELLOW)
            client_png_path = None

        # Server-side render of the same canvas state
        server_png_path = self.output_dir / "server-render.png"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{BASE_URL}/canvas.png",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if resp.status_code == 200:
                    server_png_path.write_bytes(resp.content)
                    self.log(f"Server render: {server_png_path.name}", MAGENTA)
                else:
                    self.log(f"Server render failed: HTTP {resp.status_code}", YELLOW)
                    server_png_path = None
        except Exception as e:
            self.log(f"Server render failed: {e}", YELLOW)
            server_png_path = None

        if client_png_path and server_png_path:
            try:
                self.parity_diff = self._compose_parity(
                    server_png_path.read_bytes(),
                    client_png_path.read_bytes(),
                    self.output_dir / "parity.png",
                )
                self.log(
                    f"Parity: mean diff {self.parity_diff:.2f}/255 → parity.png", GREEN
                )
            except Exception as e:
                self.log(f"Parity compose failed: {e}", YELLOW)

    @staticmethod
    def _compose_parity(server_png: bytes, client_png: bytes, out: Path) -> float:
        """Side-by-side server vs client render with a diff heatmap."""
        from PIL import Image, ImageChops, ImageDraw, ImageStat

        server = Image.open(BytesIO(server_png)).convert("RGB")
        client = Image.open(BytesIO(client_png)).convert("RGB")
        if client.size != server.size:
            client = client.resize(server.size)

        diff = ImageChops.difference(server, client)
        mean_diff = sum(ImageStat.Stat(diff).mean) / 3
        heat = diff.point(lambda v: min(255, v * 4))

        w, h = server.size
        label_h, gutter = 22, 8
        sheet = Image.new("RGB", (w * 3 + gutter * 2, h + label_h), "#222222")
        draw = ImageDraw.Draw(sheet)
        panels = [
            (server, "server (painting.py)"),
            (client, "client (stamping.ts)"),
            (heat, f"diff x4 (mean {mean_diff:.2f})"),
        ]
        for i, (img, label) in enumerate(panels):
            x = i * (w + gutter)
            draw.text((x + 6, 5), label, fill="#ffffff")
            sheet.paste(img, (x, label_h))
        sheet.save(out)
        return mean_diff

    def create_contact_sheet(self, max_frames: int = 48) -> Path | None:
        """Grid of captured frames with timestamps, for one-glance review."""
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return None

        frames = sorted(self.output_dir.glob("[0-9]*.png"))
        if not frames:
            return None
        if len(frames) > max_frames:
            step = len(frames) / max_frames
            frames = [frames[int(i * step)] for i in range(max_frames)]

        cell_w = 240
        cols = min(6, len(frames))
        rows = (len(frames) + cols - 1) // cols
        caption_h = 16

        first = Image.open(frames[0])
        cell_h = int(first.height * cell_w / first.width) + caption_h

        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#1a1a1a")
        draw = ImageDraw.Draw(sheet)
        for i, frame in enumerate(frames):
            img = Image.open(frame).convert("RGB")
            thumb_h = int(img.height * cell_w / img.width)
            img = img.resize((cell_w, thumb_h))
            x = (i % cols) * cell_w
            y = (i // cols) * cell_h
            sheet.paste(img, (x, y))
            draw.text((x + 4, y + thumb_h + 2), frame.stem, fill="#dddddd")

        out = self.output_dir / "contact-sheet.png"
        sheet.save(out)
        self.log(f"Contact sheet: {out.name}", GREEN)
        return out

    def write_report(self) -> Path:
        """Write report.md: event timeline aligned with screenshots."""
        duration = time.monotonic() - self.start_time
        lines = [
            f'# Visual Flow Test — "{self.prompt}"',
            "",
            f"- Date: {datetime.now().isoformat(timespec='seconds')}",
            f"- App: {'Vite web' if self.is_web else 'Expo mobile'} (port {self.expo_port})",
            f"- Viewport: {self.viewport[0]}x{self.viewport[1]} @2x",
            f"- Duration: {duration:.1f}s",
            f"- Agent finished: {'yes' if self.agent_idle else 'NO (timeout)'}",
            f"- Stroke batches: {self.batch_count} ({self.stroke_count} strokes)",
            f"- Thinking: {self.thinking_count} messages, {self.thinking_chars} chars",
        ]
        if self.parity_diff is not None:
            lines.append(
                f"- Client/server parity: mean diff {self.parity_diff:.2f}/255 (see parity.png)"
            )
        if self.client_state:
            cs = self.client_state
            painted = cs.get("strokesPainted", "?")
            lines.append(
                f"- Client state at end: {painted} strokes painted "
                f"(server sent {self.stroke_count}), {cs.get('bufferLength', '?')} items queued, "
                f"{cs.get('revealedChars', '?')} monologue chars revealed"
            )
            if isinstance(painted, int) and painted < self.stroke_count:
                lines.append(
                    "  - WARNING: client performance lagged behind the server; parity.png "
                    "compares an incomplete client canvas against the full server render"
                )
        if self.critiques:
            lines.append("")
            lines.append("## Critique verdicts")
            for i, critique in enumerate(self.critiques, 1):
                lines.append(f"{i}. {critique}")

        lines += [
            "",
            "## Final result",
            "",
            "![final canvas](final-canvas.png)",
            "",
            "![parity](parity.png)",
            "",
            "## Timeline",
            "",
        ]

        # Aggregate thinking text between other events so the timeline reads
        # as: thought → action → screenshot.
        pending_thinking: list[str] = []

        def flush_thinking() -> None:
            if pending_thinking:
                text = " ".join(pending_thinking)
                if len(text) > 600:
                    text = text[:600] + "…"
                lines.append(f"> {text}")
                lines.append("")
                pending_thinking.clear()

        for event in self.events:
            t = event["timestamp"]
            etype = event["type"]
            data = event.get("data", {})

            if etype in ("ws:thinking", "ws:thinking_delta"):
                text = data.get("thinking") or data.get("text") or ""
                if text:
                    pending_thinking.append(text)
                continue

            if etype == "screenshot":
                flush_thinking()
                name = data.get("filename", "")
                lines.append(f"`{t:6.1f}s` ![{name}]({name})")
                lines.append("")
            elif etype == "canvas_capture":
                flush_thinking()
                name = data.get("filename", "")
                lines.append(f"`{t:6.1f}s` canvas ![{name}]({name})")
                lines.append("")
            elif etype == "state_transition":
                flush_thinking()
                lines.append(f"`{t:6.1f}s` **state** {data.get('from')} → {data.get('to')}")
            elif etype == "ws:agent_strokes_ready":
                flush_thinking()
                lines.append(f"`{t:6.1f}s` **strokes ready** count={data.get('count', '?')}")
            elif etype == "ws:tool_use":
                if data.get("status") == "completed":
                    flush_thinking()
                    lines.append(f"`{t:6.1f}s` **tool** {data.get('name', '?')}")
            elif etype == "ws:code_execution":
                if data.get("status") == "completed":
                    flush_thinking()
                    tool = data.get("tool_name") or data.get("name") or "?"
                    if tool == "critique_canvas":
                        summary = extract_critique_summary(data.get("stdout") or "")
                        lines.append(f"`{t:6.1f}s` **critique** {summary[:500]}")
                    else:
                        rc = data.get("return_code")
                        lines.append(f"`{t:6.1f}s` **exec** {tool} rc={rc}")
            elif etype == "ws:error":
                flush_thinking()
                lines.append(f"`{t:6.1f}s` **ERROR** {str(data)[:300]}")
            elif etype in ("prompt_entered", "prompt_submitted"):
                lines.append(f"`{t:6.1f}s` **{etype}** {data.get('prompt', '')}")

        flush_thinking()

        report_path = self.output_dir / "report.md"
        report_path.write_text("\n".join(lines))
        return report_path

    def write_summary(self) -> None:
        """Write test summary to file."""
        duration = time.monotonic() - self.start_time

        events_path = self.output_dir / "events.json"
        with open(events_path, "w") as f:
            json.dump(self.events, f, indent=2)

        summary = [
            "Visual Flow Test Summary",
            "========================",
            "",
            f"Prompt: {self.prompt}",
            f"Duration: {duration:.1f}s",
            f"Screenshots: {self.screenshot_count} (+{self.canvas_capture_count} canvas crops)",
            f"Stroke batches: {self.batch_count} ({self.stroke_count} strokes)",
            f"Thinking messages: {self.thinking_count}",
            f"Critiques: {len(self.critiques)}",
            f"Agent finished: {'Yes' if self.agent_idle else 'No (timeout)'}",
        ]
        if self.parity_diff is not None:
            summary.append(f"Client/server parity mean diff: {self.parity_diff:.2f}/255")
        summary += [
            "",
            f"Output directory: {self.output_dir}",
            "Start with report.md, contact-sheet.png, and parity.png",
        ]

        summary_path = self.output_dir / "summary.txt"
        with open(summary_path, "w") as f:
            f.write("\n".join(summary))

        print(f"\n{GREEN}{'=' * 50}{RESET}")
        for line in summary:
            print(line)
        print(f"{GREEN}{'=' * 50}{RESET}")

    def create_and_open_video(self) -> Path | None:
        """Create timelapse video and open in default viewer."""
        if not shutil.which("ffmpeg"):
            self.log("ffmpeg not found, skipping video creation", YELLOW)
            return None

        output_video = self.output_dir / "timelapse.mp4"
        self.log("[VIDEO] Creating timelapse...", CYAN)

        cmd = [
            "ffmpeg", "-y",
            "-framerate", "4",
            "-pattern_type", "glob",
            "-i", f"{self.output_dir}/[0-9]*.png",
            "-vf", "scale=600:-2",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output_video),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.log(f"[VIDEO] ffmpeg failed: {result.stderr[:200]}", RED)
            return None

        self.log(f"[VIDEO] Created: {output_video}", GREEN)

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

        self.log("Getting auth token...", CYAN)
        self.token = await get_token()

        if self.do_teardown:
            await full_teardown(self.token, self.clear_canvas)

        await self.setup_browser()

        self.start_time = time.monotonic()
        stop_event = asyncio.Event()

        self.ws_monitor_task = asyncio.create_task(self.websocket_monitor(stop_event))

        self.log("Waiting for WebSocket init...", CYAN)
        if not await self.wait_for_ws_ready(timeout=10.0):
            self.log("WebSocket init timeout - continuing anyway", YELLOW)

        try:
            # Initial screenshot (home panel / studio)
            await self.take_screenshot("initial")

            self.log(f'[UI] Entering prompt: "{self.prompt}"', CYAN)
            await self.enter_studio_via_ui()
            self.log("[UI] Submitted", GREEN)

            await self.take_screenshot("submitted")

            # Interval screenshots until stopped or timeout
            end_time = self.start_time + self.timeout
            while not stop_event.is_set() and time.monotonic() < end_time:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.interval)
                except TimeoutError:
                    await self.take_screenshot()
                    await self.sample_client_state()

            if not stop_event.is_set():
                self.log("Timeout reached", YELLOW)

            # Final settled frames + parity while the browser is still up
            await self.finalize_captures()

        finally:
            stop_event.set()
            for task in list(self._pending_captures):
                task.cancel()
            if self.ws_monitor_task:
                try:
                    await asyncio.wait_for(self.ws_monitor_task, timeout=2.0)
                except (TimeoutError, asyncio.CancelledError):
                    self.ws_monitor_task.cancel()

            if self.browser:
                await self.browser.close()
            if hasattr(self, "playwright"):
                await self.playwright.stop()

        self.log(
            f"[COMPLETE] Batches: {self.batch_count}, Strokes: {self.stroke_count}, "
            f"Thinking: {self.thinking_count}, Screenshots: {self.screenshot_count}",
            GREEN,
        )

        report = self.write_report()
        self.log(f"Report: {report}", GREEN)
        self.create_contact_sheet()
        self.write_summary()

        if self.create_video and self.screenshot_count > 0:
            self.create_and_open_video()

        return self.agent_idle


def parse_viewport(viewport_str: str) -> tuple[int, int]:
    parts = viewport_str.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Invalid viewport: {viewport_str} (use WxH)")
    return int(parts[0]), int(parts[1])


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Visual flow test: observe the agent painting end-to-end.",
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
        help=f"App port (default: {DEFAULT_EXPO_PORT}; 5173 for Vite web)",
    )
    parser.add_argument(
        "--viewport",
        type=parse_viewport,
        help="Viewport WxH (default: 390x844 mobile, 1280x900 web)",
    )
    parser.add_argument(
        "--renderer",
        type=str,
        choices=["svg", "freehand"],
        default="svg",
        help="Mobile renderer to select: svg or freehand (default: svg)",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Treat the app as the Vite web studio (auto-detected for port 5173)",
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
        viewport=args.viewport,
        headless=not args.no_headless,
        clear_canvas=not args.no_clear,
        do_teardown=not args.no_teardown,
        create_video=not args.no_video,
        renderer=args.renderer,
        web=True if args.web else None,
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
