"""Server threads have room for the C recursion Python's recursion limit allows."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import code_monet


def test_package_import_sets_glibc_sized_thread_stacks() -> None:
    # stack_size() with no argument also *resets* the size to the default; restore it.
    size = threading.stack_size()
    threading.stack_size(size)
    assert size == code_monet.THREAD_STACK_BYTES == 8 << 20


def test_deeply_nested_json_on_a_worker_thread_raises_instead_of_crashing() -> None:
    def parse() -> str:
        try:
            json.loads("[" * 100_000)
        except RecursionError:
            return "RecursionError"
        return "parsed"

    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(parse).result() == "RecursionError"
