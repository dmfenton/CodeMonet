"""Production entrypoint: uvicorn, plus a clean stop when the server is idle.

The idle watcher (code_monet.idle) sets uvicorn's should_exit, which runs the
normal graceful shutdown and exits 0. The container's on-failure restart
policy leaves a clean exit stopped until the host's waker starts it again;
a crash still restarts. Development runs `python -m code_monet.main` with
reload and never idles out.
"""

from __future__ import annotations

import uvicorn

from code_monet.config import settings
from code_monet.main import app


def main() -> None:
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))

    def request_exit() -> None:
        server.should_exit = True

    app.state.request_exit = request_exit
    server.run()


if __name__ == "__main__":
    main()
