# Architecture Issues

Outstanding issues identified during architecture review (2026-01-12).

## Fixed in commit 5e72afa

- [x] Registry lock blocks all users during workspace load (CRITICAL)
- [x] State modification without lock protection
- [x] Pending strokes batch_id race condition
- [x] No JSON error handling in WebSocket loop
- [x] Sync image rendering blocks event loop
- [x] Gallery list scans all files (O(N))
- [x] SSH open to 0.0.0.0/0
- [x] Container runs as root
- [x] No connection limit per user
- [x] Instance too small (t3.small → t3.medium)
- [x] Missing websocket handler exports

## Fixed (pending commit)

**Backend:**

- [x] Agent loop uses polling → Event-driven wake-up with `asyncio.Event`
  - New `RateLimiter` class with tests (`rate_limiter.py`, `test_rate_limiter.py`)
  - Orchestrator wake tests (`test_orchestrator_wake.py`)
- [x] No rate limiting on drawing operations → 60 strokes/min limit, 1000 pending strokes max
  - Thread-safe `RateLimiter` class with sliding window algorithm
  - Configurable via `max_strokes_per_minute`, `max_pending_strokes` settings
- [x] No size limits on workspace files → 10MB max, auto-truncate old strokes
  - Configurable via `max_workspace_size_bytes` setting
  - Workspace limit tests (`test_workspace_limits.py`)
- [x] Monologue saves → Added debounce mechanism to workspace save
  - `save(debounce_ms=N)` parameter for coalescing rapid saves

**Frontend:**

- [x] MessageBubble not memoized → Wrapped with `React.memo()`
- [x] Memory leak in message tracking → Proper cleanup in useEffect, timeout refs
- [x] No cleanup on unmount for useStrokeAnimation → Reset refs on unmount, check during animation
- [x] Token refresh not debounced → New `useTokenRefresh` hook with mutex pattern
- [x] agentStroke not cleared on LOAD_CANVAS → Clear both currentStroke and agentStroke

**Type Safety:**

- [x] `PendingStrokeDict` TypedDict for pending stroke structure
- [x] `PointDict` TypedDict for point dictionaries
- [x] Proper `Settings` type annotation in workspace save methods

---

## Medium Priority - Infrastructure

### No centralized logging

- **Location:** `deploy/docker-compose.prod.yml` (in dmfenton/compute)
- **Impact:** Logs only available via `docker logs` on EC2
- **Fix:** Add `--log-driver=awslogs` or fluentd sidecar

### No container resource limits

- **Location:** `deploy/docker-compose.prod.yml` (in dmfenton/compute)
- **Impact:** Runaway process can consume entire instance
- **Fix:** Add `deploy.resources.limits` for CPU and memory

### Static GitHub Actions credentials

- **Location:** `infrastructure/github_actions.tf`
- **Impact:** Long-lived credentials, no rotation
- **Fix:** Use GitHub OIDC identity provider with assume role

### Slow alarm detection (10 min)

- **Location:** `infrastructure/monitoring.tf`
- **Impact:** CPU/memory/disk alarms take 10 min to trigger
- **Fix:** Reduce to 1 evaluation period

### Data volume not monitored

- **Location:** `infrastructure/user_data.sh:34-54`
- **Impact:** CloudWatch agent only monitors `/`, not `/home/ec2-user/data`
- **Fix:** Add data volume to CloudWatch agent config

---

## Low Priority

### No VPC Flow Logs

- **Location:** `infrastructure/vpc.tf`
- **Impact:** Can't audit network traffic for security incidents
- **Fix:** Enable VPC Flow Logs to CloudWatch

### No WAF/DDoS protection

- **Impact:** Nginx exposed directly to internet
- **Fix:** Add AWS WAF on Elastic IP or ALB

### Short backup retention (7 days)

- **Location:** `infrastructure/backup.tf:46-48`
- **Impact:** May be insufficient for compliance
- **Fix:** Add secondary retention rule for monthly archives

### No Terraform state backend

- **Location:** `infrastructure/main.tf:12-16`
- **Impact:** State stored locally, no locking
- **Fix:** Enable S3 backend with DynamoDB locking

### No dependency scanning

- **Location:** `.github/workflows/ci.yml`
- **Impact:** Vulnerabilities in dependencies not detected
- **Fix:** Add `pip-audit` for Python, `npm audit` for Node

### No supply chain security

- **Impact:** No signature verification for base images
- **Fix:** Use image signatures or SBOM

---

## Notes

- Issues are grouped by priority and category
- File:line references point to the location of the issue
- Some issues may have dependencies on others
