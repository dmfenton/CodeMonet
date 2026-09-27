"""Drawing Agent - Autonomous AI artist server."""

import threading

__version__ = "0.1.0"

# Threads get glibc's default 8 MiB stack. musl (the Alpine image) defaults to
# ~128 KiB, too small for C recursion that Python's recursion limit allows:
# json.loads of a deeply nested, program-written reveal.json on a worker thread
# overflowed it and segfaulted the whole server instead of raising
# RecursionError. Set here, before any code_monet module can start a thread.
THREAD_STACK_BYTES = 8 << 20
threading.stack_size(THREAD_STACK_BYTES)
