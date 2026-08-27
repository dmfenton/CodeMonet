from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_runtime_image_has_no_build_package_managers() -> None:
    dockerfile = (ROOT / "server/Dockerfile").read_text()
    runtime = dockerfile.split("FROM python:3.12-alpine@sha256:", maxsplit=2)[2]

    assert "COPY --from=ghcr.io/astral-sh/uv" not in runtime
    assert 'CMD ["/app/server/.venv/bin/uvicorn",' in runtime
    assert "/usr/local/bin/pip*" in runtime
    assert "/usr/local/bin/wheel" in runtime


def test_release_deploys_full_source_sha() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text()

    assert workflow.count('--parameters "ImageTag=$GITHUB_SHA"') == 2
    assert workflow.count(":$GITHUB_SHA") >= 6
