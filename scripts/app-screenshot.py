#!/usr/bin/env python3
"""Expo app screenshot tool using Playwright.

Captures screenshots of the Expo mobile app running in web mode for debugging.

Usage:
    uv run python scripts/app-screenshot.py [options]

Examples:
    uv run python scripts/app-screenshot.py              # Screenshot current state
    uv run python scripts/app-screenshot.py --auth       # With dev token auth
    uv run python scripts/app-screenshot.py --wait 3     # Wait 3 seconds before capture
    uv run python scripts/app-screenshot.py --selector "[data-testid='canvas-view']"
    uv run python scripts/app-screenshot.py --path /gallery
    uv run python scripts/app-screenshot.py --viewport 430x932  # iPhone 15 Pro Max

Options:
    --auth              Inject dev token for authenticated screens
    --wait N            Wait N seconds before screenshot (for animations/loading)
    --selector S        Wait for CSS selector before capture
    --path P            URL path (default: /, or /studio for 5173 with --auth)
    --viewport WxH      Custom viewport (default: 390x844 iPhone 14 Pro)
    --expo-port PORT    App port (8081 Expo mobile, 5173 Vite web; default: 8081)
    --backend-port PORT Backend server port for auth (default: 8000)
    --canvas-only       Capture only the canvas element (the painting itself)
    --out FILE          Output file path (default: screenshots/app-{timestamp}.png)

Prerequisites:
    - Expo web server running: cd app && npx expo start --web
    - Backend server running (if using --auth): make server
    - Playwright installed: uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Constants
DEFAULT_EXPO_PORT = 8081
DEFAULT_BACKEND_PORT = 8000
DEFAULT_VIEWPORT = (390, 844)  # iPhone 14 Pro
SCREENSHOT_DIR = Path("screenshots")

# Output format (can be extended like diagnose.py if needed)
OUTPUT_FORMAT = "rich"
if "--json" in sys.argv:
    OUTPUT_FORMAT = "json"
    sys.argv = [a for a in sys.argv if a != "--json"]

console: Console | None = None
if OUTPUT_FORMAT == "rich":
    try:
        from rich.console import Console

        console = Console()
    except ImportError:
        # Fall back to plain output
        OUTPUT_FORMAT = "plain"


def print_status(msg: str, style: str = "cyan") -> None:
    """Print a status message."""
    if OUTPUT_FORMAT == "rich" and console:
        console.print(f"[{style}]{msg}[/{style}]")
    else:
        print(msg)


def print_error(msg: str) -> None:
    """Print an error message."""
    if OUTPUT_FORMAT == "rich" and console:
        console.print(f"[red]Error: {msg}[/red]")
    else:
        print(f"Error: {msg}", file=sys.stderr)


def print_success(msg: str) -> None:
    """Print a success message."""
    if OUTPUT_FORMAT == "rich" and console:
        console.print(f"[green]{msg}[/green]")
    else:
        print(msg)


def get_auth_token(backend_port: int) -> str | None:
    """Fetch dev token from backend server."""
    try:
        import httpx

        response = httpx.get(
            f"http://localhost:{backend_port}/auth/dev-token",
            timeout=5.0,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            print_error(f"Failed to get dev token: HTTP {response.status_code}")
            return None
    except httpx.ConnectError:
        print_error(
            f"Cannot connect to backend at localhost:{backend_port}. "
            "Is the server running? (make server)"
        )
        return None
    except Exception as e:
        print_error(f"Failed to get auth token: {e}")
        return None


def parse_viewport(viewport_str: str) -> tuple[int, int]:
    """Parse viewport string like '390x844' into (width, height)."""
    try:
        parts = viewport_str.lower().split("x")
        if len(parts) != 2:
            raise ValueError("Invalid format")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        print_error(f"Invalid viewport format: {viewport_str}. Use WxH (e.g., 390x844)")
        sys.exit(1)


def screenshot_app(
    path: str = "/",
    auth: bool = False,
    wait: float = 0,
    selector: str | None = None,
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
    expo_port: int = DEFAULT_EXPO_PORT,
    backend_port: int = DEFAULT_BACKEND_PORT,
    start_prompt: str | None = None,
    canvas_only: bool = False,
    out: str | None = None,
) -> str | None:
    """Take a screenshot of the Expo web app.

    Args:
        path: URL path to navigate to
        auth: Whether to inject dev token for authentication
        wait: Seconds to wait before screenshot
        selector: CSS selector to wait for before capture
        viewport: (width, height) tuple for viewport size
        expo_port: Expo web server port
        backend_port: Backend server port (for auth token)
        start_prompt: If provided, enter this prompt in HomePanel and submit to enter studio

    Returns:
        Path to saved screenshot, or None on failure
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print_error(
            "Playwright not installed. Run:\n"
            "  cd server && uv sync --extra dev\n"
            "  uv run playwright install chromium"
        )
        return None

    # Ensure screenshot directory exists
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    # Generate filename with timestamp (or use explicit --out)
    if out:
        filename = Path(out)
        filename.parent.mkdir(parents=True, exist_ok=True)
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = SCREENSHOT_DIR / f"app-{timestamp}.png"

    # Get auth token if needed
    token = None
    if auth:
        print_status("Fetching dev token from backend...")
        token = get_auth_token(backend_port)
        if not token:
            return None
        print_status("Got auth token", "green")

    print_status(f"Launching browser with viewport {viewport[0]}x{viewport[1]}...")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            device_scale_factor=2,  # Retina-like screenshots
        )

        # Inject auth token before navigation
        if token:
            # Use json.dumps to safely escape the token for JavaScript
            token_js = json.dumps(token)
            context.add_init_script(f"""
                localStorage.setItem('access_token', {token_js});
                localStorage.setItem('refresh_token', {token_js});
                localStorage.setItem('auth_access_token', {token_js});
                localStorage.setItem('auth_refresh_token', {token_js});
            """)
            print_status("Injected auth token into localStorage")

        page = context.new_page()

        # Navigate to the app
        url = f"http://localhost:{expo_port}{path}"
        print_status(f"Navigating to {url}...")

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print_error(
                f"Failed to load {url}: {e}\n"
                f"Is Expo web server running? (cd app && npx expo start --web)"
            )
            browser.close()
            return None

        # If start_prompt provided, enter it via HomePanel to transition to studio
        if start_prompt:
            print_status(f"Entering prompt via HomePanel: {start_prompt}")
            input_selector = '[data-testid="home-prompt-input"]'
            submit_selector = '[data-testid="home-prompt-submit"]'

            try:
                # Wait for home panel input
                page.wait_for_selector(input_selector, timeout=10000)
                print_status("Found home panel input", "green")

                # Fill the prompt
                page.fill(input_selector, start_prompt)
                page.wait_for_timeout(200)  # Brief pause for state update

                # Click submit
                page.click(submit_selector)
                print_status("Submitted prompt", "green")

                # Wait for transition to studio (canvas should appear)
                canvas_selector = '[data-testid="canvas-view"]'
                page.wait_for_selector(canvas_selector, timeout=10000)
                print_status("Entered studio mode", "green")

            except Exception as e:
                print_error(f"Failed to enter via HomePanel: {e}")
                # Continue anyway, take screenshot of current state

        # Wait for specific selector if provided
        if selector:
            print_status(f"Waiting for selector: {selector}...")
            try:
                page.wait_for_selector(selector, timeout=10000)
                print_status("Selector found", "green")
            except Exception as e:
                print_error(f"Selector not found: {selector} - {e}")
                # Continue anyway, take screenshot of current state

        # Additional wait if specified
        if wait > 0:
            print_status(f"Waiting {wait} seconds...")
            page.wait_for_timeout(int(wait * 1000))

        # Take screenshot
        if canvas_only:
            canvas_selector = '[data-testid="canvas-view"]'
            print_status("Capturing canvas element only...")
            try:
                page.wait_for_selector(canvas_selector, timeout=10000)
                page.locator(canvas_selector).screenshot(path=str(filename))
            except Exception as e:
                print_error(f"Canvas element not found, capturing viewport: {e}")
                page.screenshot(path=str(filename), full_page=False)
        else:
            print_status("Taking screenshot...")
            page.screenshot(path=str(filename), full_page=False)

        browser.close()

    print_success(f"Saved: {filename}")
    return str(filename)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Capture screenshots of Expo mobile app in web mode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python scripts/app-screenshot.py --auth
  uv run python scripts/app-screenshot.py --wait 2 --selector "[data-testid='canvas-view']"
  uv run python scripts/app-screenshot.py --path /gallery --auth

Prerequisites:
  - Expo web server: cd app && npx expo start --web
  - Backend server (for --auth): make server
  - Playwright: uv run playwright install chromium
        """,
    )

    parser.add_argument(
        "--path",
        default=None,
        help="URL path to navigate to (default: /, or /studio for 5173 with --auth)",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Inject dev token for authenticated screens",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=0,
        metavar="SECONDS",
        help="Wait N seconds before screenshot",
    )
    parser.add_argument(
        "--selector",
        help="Wait for CSS selector before capture",
    )
    parser.add_argument(
        "--viewport",
        default="390x844",
        help="Custom viewport WxH (default: 390x844 iPhone 14 Pro)",
    )
    parser.add_argument(
        "--expo-port",
        type=int,
        default=DEFAULT_EXPO_PORT,
        help=f"Expo web server port (default: {DEFAULT_EXPO_PORT})",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=DEFAULT_BACKEND_PORT,
        help=f"Backend server port for auth (default: {DEFAULT_BACKEND_PORT})",
    )
    parser.add_argument(
        "--start-prompt",
        metavar="PROMPT",
        help="Enter this prompt via HomePanel to start drawing and enter studio mode",
    )
    parser.add_argument(
        "--canvas-only",
        action="store_true",
        help="Capture only the canvas element ([data-testid='canvas-view'])",
    )
    parser.add_argument(
        "--out",
        metavar="FILE",
        help="Output file path (default: screenshots/app-{timestamp}.png)",
    )

    args = parser.parse_args()

    # Validate wait time
    if args.wait < 0:
        print_error("--wait must be a non-negative number")
        sys.exit(1)

    viewport = parse_viewport(args.viewport)

    # The Vite web studio lives at /studio; default there when authenticated
    if args.path is None:
        path = "/studio" if (args.expo_port == 5173 and args.auth) else "/"
    else:
        path = args.path

    result = screenshot_app(
        path=path,
        auth=args.auth,
        wait=args.wait,
        selector=args.selector,
        viewport=viewport,
        expo_port=args.expo_port,
        backend_port=args.backend_port,
        start_prompt=args.start_prompt,
        canvas_only=args.canvas_only,
        out=args.out,
    )

    if result is None:
        sys.exit(1)

    # Print final path for easy copy/paste
    print(f"\nScreenshot saved to: {result}")


if __name__ == "__main__":
    main()
