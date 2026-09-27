"""Image check: worker threads survive deep C recursion (musl's small default stack).

    docker run --rm -i --entrypoint /app/server/.venv/bin/python IMAGE - < server/docker/check_thread_stack.py

Untrusted, program-written JSON is parsed on worker threads; with musl's
default thread stack a deeply nested document segfaulted the server.
"""

import json
from concurrent.futures import ThreadPoolExecutor

import code_monet  # noqa: F401  (sets the thread stack size)


def parse_deeply_nested() -> str:
    try:
        json.loads("[" * 100_000)
    except RecursionError:
        return "RecursionError"
    return "parsed"


with ThreadPoolExecutor(1) as pool:
    outcome = pool.submit(parse_deeply_nested).result()
assert outcome == "RecursionError", outcome
print("worker thread stack: ok")
