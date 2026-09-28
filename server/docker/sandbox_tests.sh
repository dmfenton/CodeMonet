#!/bin/sh
# Run the painting and performance tests inside the server image, where paint
# programs run confined (Landlock + seccomp). On macOS they run unconfined, so a
# test that relies on writing outside the run's output directory passes there
# and fails in CI.   make sandbox-tests
set -e
cd /app/server
/app/server/.venv/bin/python -m ensurepip > /tmp/ensurepip.log 2>&1 || { cat /tmp/ensurepip.log; exit 1; }
/app/server/.venv/bin/python -m pip install -q --disable-pip-version-check pytest pytest-asyncio httpx
cp -r /src-tests /app/server/tests
/app/server/.venv/bin/python -c "from code_monet import sandbox; assert sandbox.available(), 'no sandbox'"
exec /app/server/.venv/bin/python -m pytest -q -p no:cacheprovider -o asyncio_mode=auto \
    tests/test_program_painting.py tests/test_performance.py
