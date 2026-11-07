# Infrastructure (AWS)

> **Infrastructure has moved.** EC2, VPC, ECR, Route 53, SES, monitoring, IAM, and the nginx vhost router all live in **[dmfenton/compute](https://github.com/dmfenton/compute)** now. This doc only covers what's still owned by CodeMonet: the release flow, sleep-on-idle and the pre-rendered public site. The edge and host side (nginx routes, `codemonet-waker`, cache, monitoring) is documented in `platform.dmfenton.net/ops/CLAUDE.md` ("CodeMonet sleep-on-idle").

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

1. Runs server tests
2. Builds the web frontend (`web/dist/client` for nginx, `web/dist/prerender` for the backend image) and syncs the client build to S3
3. Builds the backend Docker image (it carries `web/dist/prerender`) and pushes it to AWS ECR
4. Runs database migrations via SSM
5. Creates GitHub Release with changelog
6. Deploys to EC2 via SSM (`Compute-DeployCodeMonet`): recreates `drawing-agent`, health-gates it, proves it has no AWS path, then warms nginx's public cache
7. Verifies `/api/version` reports the new version and nginx serves the pre-rendered `/gallery`

The platform's operations release must ship first whenever this repo's release
depends on a new edge or host contract (see the platform runbook).

## Sleep-on-idle

`drawing-agent` runs nothing without a client: workspaces start on WebSocket
connect, pause on disconnect and are torn down 300 s later. So after
`IDLE_EXIT_MINUTES` (default 15; `0` disables) with no WebSocket and no
non-health HTTP request, the server stops itself cleanly and exits 0
(`server/code_monet/idle.py`, run by the production entrypoint
`python -m code_monet.serve`). `/health` is never activity: the container
healthcheck, deploy gates and probes cannot keep it awake.

The container's restart policy is `on-failure`: a clean idle exit stays
stopped, a crash (non-zero exit) restarts. On the host, the platform's
`codemonet-waker` service starts the stopped container when nginx gets a
gateway error from any `drawing-agent` route: a GET is redirected (307) to the
same URI once `/health` answers; other methods and WebSocket upgrades get 503
with `Retry-After`, and both clients already reconnect (web: every 3 s; iOS:
jittered backoff from 3 s). Measured cold start is in the platform runbook.
`python -m code_monet.main` (development) never idles out.

## Pre-rendered public site

There is no SSR server in production. The public pages are rendered once per
change and served by nginx as static files:

```
Browser Request
      |
    nginx (443)
      |
  /assets/*, static files      -> web/dist/client (cached)
  /, /gallery, /gallery/u/p    -> pre-rendered HTML, else the SPA shell
  /sitemap.xml                 -> pre-rendered
  /api/public/gallery (list),
  .../thumbnail.png            -> nginx persistent cache, else drawing-agent
  /api/*, /ws, /auth/ ...      -> drawing-agent:8000, or the waker if asleep
```

- **One owner for page content.** `web/src/entry-server.tsx` renders a page
  (markup, Helmet head tags, `window.__INITIAL_DATA__`) exactly as the retired
  SSR server did. `web/src/prerender.ts` builds every public page with it and
  is bundled by `npm run build -w web` into `web/dist/prerender/prerender.mjs`
  (self-contained, next to the built `index.html` it uses as template). The
  dev server (`web/server.ts`) renders each request with the same function.
- **The server only gathers data and writes files.**
  `server/code_monet/prerender.py` reads the public galleries (the same scan
  as `/public/gallery`), runs the bundle with `node` (in the image), and
  atomically writes `index.html`, `gallery.html`, `gallery/{user}/{piece}.html`
  and `sitemap.xml` (`routes/seo.py`) into `PRERENDER_DIR` (`/app/site` in
  production, a host directory nginx mounts read-only). It runs at every
  start (deploy or wake) and after a gallery save or a publish/unpublish;
  requests during a run coalesce into one more run.
- Pages embed their data, so loading `/`, `/gallery` or a piece page never
  calls the server. A route that is not pre-rendered gets the SPA shell and
  renders on the client (`entry-client.tsx` hydrates only when there is markup).

**Building the pre-renderer locally:**

```bash
npm run build -w shared && npm run build -w web     # web/dist/{client,prerender}
cd server && uv run pytest tests/test_prerender.py   # includes a real-bundle run
```

`docker build -f server/Dockerfile .` needs `web/dist/prerender` built first.

## Terraform

All Terraform lives in [dmfenton/compute](https://github.com/dmfenton/compute/tree/main/infrastructure). The EC2 box, ECR repos (`drawing-agent`; the `web-ssr` repo is retired and unused), VPC, Route 53, SES, monitoring, IAM, and S3 deploy-config bucket (`compute-deploy-573988763875`) are all defined there.

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
uv run python scripts/remote.py shell "sqlite3 /home/ec2-user/data/codemonet/drawing_agent.db '.tables'"
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

Managed by Terraform in [compute/infrastructure/github_actions.tf](https://github.com/dmfenton/compute/blob/main/infrastructure/github_actions.tf). The IAM user has `s3:PutObject` on `compute-deploy-*` (where this repo's release workflow uploads the web build) and `ecr:*` on the `drawing-agent` repo (and the retired `web-ssr` repo).

## Required GitHub Secrets (Server)

| Secret                  | Description                      |
| ----------------------- | -------------------------------- |
| `AWS_ACCESS_KEY_ID`     | IAM user access key for ECR push |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key for ECR push |

Add at: https://github.com/dmfenton/CodeMonet/settings/secrets/actions

CodeMonet runtime state is mounted from `/home/ec2-user/data/codemonet` only.
Platform owns the one-time database/workspace move and its rollback; see
`platform.dmfenton.net/ops/scripts/isolate-codemonet-data.py`. Historical shared
logs and backups remain outside the app mount. New application logs are collected
from the private directory by the Platform-owned CloudWatch agent.
