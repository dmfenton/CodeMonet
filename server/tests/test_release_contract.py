from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_runtime_image_has_no_build_package_managers() -> None:
    dockerfile = (ROOT / "server/Dockerfile").read_text()
    runtime = dockerfile.split("FROM python:3.12-alpine@sha256:", maxsplit=2)[2]

    assert "COPY --from=ghcr.io/astral-sh/uv" not in runtime
    assert 'CMD ["/app/server/.venv/bin/uvicorn",' in runtime
    assert "RUN apk upgrade --no-cache" in runtime
    assert "/usr/local/bin/pip*" in runtime
    assert "/usr/local/bin/wheel" in runtime

    remote = (ROOT / "scripts/remote.py").read_text()
    assert '"/app/server/.venv/bin/python -m alembic upgrade head"' in remote
    assert '"uv run python -m alembic upgrade head"' not in remote

    web_dockerfile = (ROOT / "web/Dockerfile").read_text()
    web_runtime = web_dockerfile.split("FROM node:24.18.0-alpine@sha256:", maxsplit=2)[2]
    assert "RUN apk upgrade --no-cache" in web_runtime
    assert (
        "rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx"
        in web_runtime
    )


def test_release_deploys_unique_artifact_from_exact_source() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text()

    assert workflow.count('--parameters "ImageTag=$ARTIFACT_TAG"') == 2
    assert workflow.count(":$ARTIFACT_TAG") >= 6
    assert "artifact_tag=v${VERSION}-${GITHUB_SHA}-run" in workflow
    assert "Require exact main release source" in workflow
    assert 'git rev-parse HEAD)" == "$(git rev-parse origin/main)' in workflow
