# Code Monet

Built by [Daniel Fenton](https://dmfenton.net). More on the project at [dmfenton.net/sketch/code-monet](https://dmfenton.net/sketch/code-monet/).

An autonomous AI artist powered by Claude that creates drawings, observes its work, and iterates—with humans as creative collaborators.

![Demo](demo.gif) <!-- TODO: Add demo GIF -->

## What Is This?

A drawing machine with genuine creative agency. The AI comes up with its own ideas, writes code to generate drawings, watches the results appear on a shared canvas, and decides what to do next. Humans can intervene anytime—draw on the canvas, nudge the agent with suggestions, or just watch it work.

---

## Technical Highlights

### AI Agent Architecture

Built on **Anthropic's Claude Agent SDK** with a custom tool ecosystem:

- **In-process MCP tools**: Drawing tools are defined using SDK decorators and registered as an MCP server that runs in the same process as the agent
- **Multi-turn reasoning loops**: Agent sees canvas state, generates paths, observes results, iterates
- **Subprocess code execution**: The `generate_svg` tool runs agent-authored Python in a subprocess with timeout protection
- **Streaming thought process**: Real-time delivery of agent thinking to clients—full transparency into creative decisions
- **Style-aware generation**: Two distinct modes (pen plotter vs. expressive paint) with different constraints and palettes

The agent generates **path commands** (SVG paths, cubic beziers, polylines) rather than pixels—resolution-independent and infinitely scalable.

### Real-Time Collaborative Canvas

**WebSocket architecture** for real-time rendering:

- Event-driven orchestration with `asyncio.Event` (no polling)
- Per-user isolated workspaces with thread-safe multi-user support
- Graceful reconnection with full state recovery
- Shared Fenton Identity OAuth with PKCE and distributed tracing correlation

**Path interpolation engine**:

- Trapezoidal velocity profiles with easing (accelerate → cruise → decelerate)
- Pen plotter motion simulation (pen-up travel, servo settling delays)
- Client-side animation decoupled from agent execution

### Infrastructure & DevOps

**Terraform-managed AWS deployment**:

| Resource   | Purpose                                              |
| ---------- | ---------------------------------------------------- |
| EC2 + EBS  | Compute with persistent storage, automated snapshots |
| ECR        | Container registry with lifecycle policies           |
| Fenton Platform | Shared identity, PKCE magic links, RS256 tokens |
| Route 53   | DNS management                                       |
| X-Ray      | Distributed tracing with client span correlation     |
| CloudWatch | Alarms and monitoring                                |

**CI/CD pipeline**:

- Tag-based releases via GitHub Actions
- Docker builds with multi-stage optimization
- Watchtower auto-deployment (30-second rollouts)
- Deployment verification before marking releases complete

### Mobile Deployment

**Native SwiftUI iOS app via XcodeGen + Fastlane**:

- Automated TestFlight builds on version tags
- iOS Universal Links for seamless magic link sign-in
- Dynamic versioning from git tags
- `ios/CodeMonet.xcodeproj` generated from `ios/project.yml` by XcodeGen

### Observability

**End-to-end distributed tracing**:

- OpenTelemetry instrumentation (FastAPI, SQLAlchemy, logging)
- Client trace IDs propagated via WebSocket
- Full stack traces in error responses with trace_id references
- Debug endpoints for agent state, workspace files, and logs

### Code Quality

- **Python**: Strict mypy, ruff formatting, async/await throughout, Pydantic validation
- **TypeScript**: Strict mode, no `any` types, discriminated unions over runtime checks
- **Swift**: `ios/MonetKit` is a standalone SwiftPM package (protocol types, reducer, performer, renderer, networking) that builds and tests without a simulator
- **Shared library**: Platform-agnostic TypeScript used by the web app
- **Testing**: pytest (server) + Vitest (web) + `swift test` (MonetKit)

---

## Architecture

```
┌─────────────────────┐                         ┌─────────────────────┐
│  Native iOS App     │                         │                     │
│  (SwiftUI, MonetKit)│◄── WebSocket (60fps) ──►│   Python Backend    │
├─────────────────────┤                         │   (FastAPI)         │
│  Web App            │                         │                     │
│  (Vite + React)     │◄── WebSocket (60fps) ──►│  • Claude Agent SDK │
│                     │    stroke events        │  • In-process tools │
│  • SVG/raster canvas│    thinking stream      │  • Path interpolation│
│  • Real-time render │    state sync           │                     │
└─────────────────────┘                         └─────────────────────┘
         │
         │              ┌─────────────┐
         └──────────────│ shared/ (web)│
                        │ MonetKit (iOS)│
                        └─────────────┘
```

---

## Tech Stack

| Layer          | Technologies                                            |
| -------------- | ------------------------------------------------------- |
| AI             | Claude Agent SDK or OpenAI Responses API, in-process tools, subprocess exec |
| Backend        | Python 3.12+, FastAPI, SQLAlchemy async, Pydantic       |
| Frontend       | Native SwiftUI (iOS), Vite + React + TypeScript (web)   |
| Shared         | TypeScript monorepo with npm workspaces                 |
| Infrastructure | Fenton Platform, Terraform, AWS (EC2, ECR, Route 53, X-Ray) |
| CI/CD          | GitHub Actions, Fastlane, Watchtower                    |
| Observability  | OpenTelemetry, AWS X-Ray, structured logging            |

---

## Quick Start

```bash
# Clone and setup
cd CodeMonet
cp .env.example .env
# Claude development uses your isolated Claude subscription session. Production
# uses short-lived Anthropic AWS workload identity; static Anthropic keys are unsupported.
# Or set AGENT_PROVIDER=openai and OPENAI_API_KEY for the OpenAI backend.

# Install and run
make install
make dev-web
```

Server runs at `localhost:8000`, web app at `localhost:5173`. For the native
iOS app, `cd ios && make generate` then open `CodeMonet.xcodeproj` in Xcode
(or `make ios-build` for an unsigned Simulator build from the repo root).

---

## License

MIT
