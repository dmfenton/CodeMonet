"""Run an untrusted Python script confined to its working directory.

    python -I -m code_monet.confined_python SCRIPT

On Linux the process confines itself (code_monet.sandbox.python_policy) before
running SCRIPT: read-only Python and its packages, write access only to the
current directory, no network, no new processes. Elsewhere (macOS development)
it runs unconfined. Used for plotter-mode generate_svg code.
"""

from __future__ import annotations

import os
import runpy
import sys

from code_monet import sandbox


def main(argv: list[str]) -> int:
    (script,) = argv
    if sandbox.available():
        sandbox.confine(sandbox.python_policy(os.getcwd()))
    runpy.run_path(script, run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
