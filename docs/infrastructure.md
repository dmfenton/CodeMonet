# Infrastructure (AWS)

> **Infrastructure has moved.** EC2, VPC, ECR, Route 53, SES, monitoring, IAM, and the nginx vhost router all live in **[dmfenton/compute](https://github.com/dmfenton/compute)** now. This doc only covers what's still owned by CodeMonet: the release flow and the SSR architecture.

## Changelog

**Location:** `CHANGELOG.md` at project root

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Update the `[Unreleased]` section when making changes:

- **Added** - New features
- **Changed** - Changes in existing functionality
- **Fixed** - Bug fixes
- **Security** - Vulnerability fixes

Before cutting a release, move `[Unreleased]` items to a new version heading with the release date.

## Cutting a Release

Deploy to production by tagging `main`:

```bash
git checkout main
git pull origin main
git tag v1.0.0
git push origin v1.0.0
```

This triggers `.github/workflows/release.yml` which:

1. Runs E2E SDK tests to verify Claude SDK compatibility
2. Builds web frontend and syncs to S3
3. Builds backend Docker image with version tag
4. Builds SSR Docker image with version tag
5. Pushes both images to AWS ECR
6. Runs database migrations via SSM
7. Creates GitHub Release with changelog
8. Deploys to EC2 via SSM (updates IMAGE_TAG, restarts containers)
9. Verifies deployment via `/api/version` endpoint

## SSR Architecture

The web frontend uses Server-Side Rendering (SSR) for SEO and social sharing:

```
Browser Request
      |
    nginx (443)
      |
  /assets/*     -> static files (cached)
  /api/*        -> drawing-agent:8000
  /ws           -> drawing-agent:8000
  /*            -> web-ssr:3000 (SSR)
    on error    -> static index.html
```

**Components:**

- **web-ssr**: Node.js SSR server running Express + tsx
- **nginx**: Reverse proxy with smart routing and graceful fallback
- **drawing-agent**: Python backend API

**Graceful Degradation:**

1. SSR server down -> nginx serves static SPA via `@fallback`
2. SSR render error -> server.ts catches, serves static fallback
3. Backend down -> SSR returns empty initial data, client fetches on hydrate

**Health Endpoints:**

- `/ssr-health` - SSR server health check
- `/api/version` - Backend API version

**Building SSR Locally:**

```bash
# Build the SSR Docker image
docker build -f web/Dockerfile -t web-ssr:dev .

# Run locally
docker run -p 3000:3000 -e API_URL=http://host.docker.internal:8000 web-ssr:dev
```

## Terraform

All Terraform lives in [dmfenton/compute](https://github.com/dmfenton/compute/tree/main/infrastructure). The EC2 box, ECR repos (`drawing-agent`, `web-ssr`), VPC, Route 53, SES, monitoring, IAM, and S3 deploy-config bucket (`compute-deploy-573988763875`) are all defined there.

To change shared infra, open a PR against compute and follow its [RUNBOOK](https://github.com/dmfenton/compute/blob/main/docs/RUNBOOK.md).

## Remote Server Management (SSM)

Use `scripts/remote.py` to manage the server via AWS SSM (no SSH needed):

```bash
# View container logs
uv run python scripts/remote.py logs

# Restart container
uv run python scripts/remote.py restart

# Run migrations
uv run python scripts/remote.py migrate

# Create invite code
uv run python scripts/remote.py create-invite

# Create user directly
uv run python scripts/remote.py create-user EMAIL [PASSWORD]

# Run command in container
uv run python scripts/remote.py exec "command"

# Run command on host
uv run python scripts/remote.py shell "command"
```

**Note:** Commands that start Python inside the container can be slow (~30s) due to `uv run` overhead. For direct database access, use sqlite3 on the host:

```bash
uv run python scripts/remote.py shell "sqlite3 /home/ec2-user/data/code_monet.db '.tables'"
```

## SSH Access (if needed)

The instance is tagged `Name=drawing-agent` (historical name; predates compute being a shared platform). Prefer SSM Session Manager for shell access:

```bash
aws ssm start-session --target $(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=drawing-agent" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
```

The SSH key (`drawing-agent.pem`) is provisioned by compute terraform; see compute's RUNBOOK for the EIP and key handling.

## GitHub Actions IAM User

Managed by Terraform in [compute/infrastructure/github_actions.tf](https://github.com/dmfenton/compute/blob/main/infrastructure/github_actions.tf). The IAM user has `s3:PutObject` on `compute-deploy-*` (where this repo's release workflow uploads the web build) and `ecr:*` on the `drawing-agent` and `web-ssr` repos.

## Required GitHub Secrets (Server)

| Secret                  | Description                      |
| ----------------------- | -------------------------------- |
| `AWS_ACCESS_KEY_ID`     | IAM user access key for ECR push |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key for ECR push |

Add at: https://github.com/dmfenton/CodeMonet/settings/secrets/actions
