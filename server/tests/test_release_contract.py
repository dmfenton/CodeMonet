import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_runtime_image_has_no_build_package_managers() -> None:
    dockerfile = (ROOT / "server/Dockerfile").read_text()
    assert re.search(
        r"ARG FENTON_RUNTIME_IMAGE=573988763875\.dkr\.ecr\.us-east-1\.amazonaws\.com/"
        r"fenton-python-runtime@sha256:[0-9a-f]{64}\n",
        dockerfile,
    )
    assert "FROM python:" not in dockerfile
    assert "FROM ${FENTON_RUNTIME_IMAGE} AS build\n" in dockerfile
    assert "FROM node:24.18.0-alpine@sha256:" in dockerfile
    assert "COPY server/claude-cli/package*.json ./" in dockerfile
    assert "npm ci --omit=dev --ignore-scripts" in dockerfile
    runtime = dockerfile.split("FROM ${FENTON_RUNTIME_IMAGE}\n", maxsplit=1)[1]

    assert "COPY --from=ghcr.io/astral-sh/uv" not in runtime
    assert 'CMD ["/app/server/.venv/bin/python", "-m", "code_monet.serve"]' in runtime
    assert "RUN apk upgrade --no-cache" in runtime
    assert "! command -v pip" in runtime
    assert "! command -v wheel" in runtime
    assert "COPY --from=claude-cli /opt/claude/claude /usr/local/bin/claude" in runtime
    assert "SubprocessCLITransport('', ClaudeAgentOptions())._find_cli()" in runtime
    assert "subprocess.run([cli, '--version'], check=True)" in runtime
    assert 'ENV PATH="/app/server/.venv/bin:${PATH}"' in runtime

    # The pre-render bundle needs only the node binary: no npm, no node_modules.
    assert "COPY --from=claude-cli /usr/local/bin/node /usr/local/bin/node" in runtime
    assert "node_modules" not in runtime
    assert "/usr/local/bin/npm" not in runtime
    # web-ssr is retired: nginx serves the static build and pre-rendered pages.
    assert not (ROOT / "web/Dockerfile").exists()


def test_release_deploys_unique_artifact_from_exact_source() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text()

    # Migrate, then deploy, each through Platform's shared release step with the immutable tag.
    parameters = """DEPLOY_PARAMETERS: '{"ImageTag":"${{ steps.version.outputs.artifact_tag }}"}'"""
    assert workflow.count(parameters) == 2
    assert workflow.count("run: bash scripts/ci/platform-release.sh") == 2
    assert workflow.index("DEPLOY_DOCUMENT: Compute-MigrateCodeMonet") < workflow.index(
        "DEPLOY_DOCUMENT: Compute-DeployCodeMonet"
    )
    assert "aws ssm send-command" not in workflow
    helper = (ROOT / "scripts/ci/platform-release.sh").read_text()
    assert ".github/actions/deploy-release/deploy_release.py" in helper
    assert "PLATFORM_RELEASE_COMMIT=" in helper
    # One image (drawing-agent): tagged, pushed and recorded by its artifact tag.
    assert workflow.count(":$ARTIFACT_TAG") >= 3
    assert "web-ssr:" not in workflow and "ECR_SSR_REPOSITORY" not in workflow
    assert "artifact_tag=v${VERSION}-${GITHUB_SHA}-run" in workflow
    assert "Require exact main release source" in workflow
    assert 'git rev-parse HEAD)" == "$(git rev-parse origin/main)' in workflow
