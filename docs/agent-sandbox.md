# Agent Sandbox

The agent is steered by user text (directions, nudges), so everything it
executes must be treated as possibly prompt-injected: its Bash, Read, Write,
Edit, Glob and Grep tools, the painting programs it writes, and plotter-mode
`generate_svg` code. All of that runs
as the server's OS user in the server's container. The sandbox limits it to
the user's own workspace. It sits under the tools and programs, so it does not
rely on the model following instructions.

## Threat model

An injected agent or program tries to:

- read secrets: server environment (`/proc/<server>/environ`, the inherited
  env), server memory (ptrace; the host has `kernel.yama.ptrace_scope = 0`),
  the auth database, the Anthropic identity token, cloud credentials (IMDS);
- read or change another user's workspace, or publish anything it can read
  (painting outputs and programs are public for public gallery pieces);
- damage the server: kill it, chmod/truncate its files.

## Mechanism

`code_monet/sandbox.py` confines the current process and everything it later
execs, using two unprivileged kernel features. Neither needs namespaces, so the
container keeps Docker's default seccomp profile. (bubblewrap would need
user namespaces, i.e. a relaxed seccomp profile and `systempaths=unconfined`
on a host shared by every tenant; we chose not to widen that kernel surface.)

- **Landlock** (kernel 6.1 in production = ABI 2): file access only beneath the
  policy's read roots (read + execute) and write roots (full access);
  everything else, including other users, `/app/data`, and the server's
  `/proc/<pid>/environ|mem|fd` (Landlock blocks ptrace-class access to
  processes outside the sandbox), is denied. Newer kernels also get
  signal and abstract-unix-socket scoping (ABI 6).
- **seccomp** (a BPF filter, killing on unexpected architecture): denies what
  ABI 2 does not cover — path-based `chmod`/`chown`/`truncate`, `io_uring`,
  `tkill`, and signals (`kill`, `tgkill`, `rt_*sigqueueinfo`, `pidfd_open`) to
  PID 1, the server, their process groups, or everyone (`-1`). Optionally no
  network sockets but `AF_UNIX`, and no new processes (threads still work).
- The confined process starts its own session, so `kill(0)` reaches only it.

`confine()` must run single-threaded, before any untrusted code, and raises
(`SandboxError`) if it cannot apply the policy: on Linux, runs fail closed.
On macOS (development) there is no Landlock or seccomp. The environment is
still built from scratch there, but the tools and programs run unconfined.

## Policies

| Who | Read (and execute) | Write | Network | Processes |
|---|---|---|---|---|
| Claude CLI (drawing agent, critique) and everything its tools run | `/usr /lib /bin /sbin /etc /proc`, Python + venv, the CLI binary, the identity-token directory | the user's workspace, the user's Claude home, `/dev` | yes (Anthropic API) | yes |
| Painting program (`paint_runner`) | Python + venv + `sys.path`, `/lib /usr/lib` | the version's output dir, its scratch dir | no | no (threads only) |
| `generate_svg` code (`confined_python`) | same as painting | its throwaway run dir | no | no (threads only) |

The server decides each policy (`claude_runtime.claude_launch`,
`sandbox.python_policy`); the confined side only applies it.

**Claude CLI.** Every CLI process is started through the SDK's `cli_path` =
`code_monet/bin/claude-sandboxed`, which runs `code_monet.claude_sandbox`.
The server passes the launch spec in `CODE_MONET_SANDBOX` (CLI path, env,
read/write roots). The wrapper builds the CLI's environment from the spec plus
the few variables the SDK sets for the CLI (`CLAUDE_CODE_*`,
`CLAUDE_AGENT_SDK_*`, `PWD`, `TRACEPARENT`/`TRACESTATE`), so nothing else
inherited from the server gets through. It then confines itself and execs the
real CLI (the SDK's bundled build). Without a spec it refuses to run.

With workload identity each user gets a private Claude home,
`{anthropic_config_directory}/users/{user_id}`: `HOME`, `TMPDIR` (`tmp/`), and
`CLAUDE_CONFIG_DIR` (`claude/`: federation profile, access-token cache,
sessions). The CLI honours `TMPDIR`, so no shared `/tmp` is needed. In
development without workload identity the CLI uses the developer's own login
(`HOME`).

**Painting programs and `generate_svg` code.** `paint_runner` confines itself
before importing numpy or anything else, then runs the program;
`generate_svg` scripts run via `python -I -m code_monet.confined_python`, which
confines itself and then runs the script. See
[program-painting.md](program-painting.md#untrusted-programs) for the
environment and the published-asset checks.

## Residual risks

- The agent can read its own user's Anthropic access token and identity token
  (the CLI needs them), and has network access. It can therefore spend API
  quota as the service account until the token expires. The token grants no
  AWS access.
- Network: the CLI (and so the agent's shell) can reach anything the
  container can, including other containers on the app network and, until
  the container is taken off IMDS, the instance metadata service. That
  is fixed in the platform's ops config, not here.
- Signals to *other users'* agent processes (not the server) are not blocked
  on ABI < 6, so one agent could disrupt another's turn. It cannot read or
  change the other user's data.
- Metadata: `stat` of paths outside the policy is not restricted, so file
  existence and sizes are visible, but not contents or directory listings.
  Likewise other processes' `/proc/<pid>/cmdline|status` (e.g. another user's
  agent command line) are readable; their environment and memory are not.
- The CLI's environment passes through variables named `CLAUDE_CODE_*` and
  `CLAUDE_AGENT_SDK_*` from the server (the SDK's own settings). Never give a
  server secret such a name.
- No memory or CPU cgroup limits; painting runs are bounded by
  `PAINT_TIMEOUT_S` and cannot fork.

## Verification

- `tests/test_sandbox.py`: filter assembly, launch policy, CLI environment;
  on Linux, a confined subprocess is checked against a probe matrix at native
  and at production's ABI 2, alongside an unconfined baseline showing the probe
  detects access.
- `make sandbox-e2e` (also in CI's Docker job on `main`): in the real server
  image, with no credentials. A mock Anthropic API drives the real SDK and CLI
  through the wrapper to make hostile Bash/Read/Grep tool calls, and hostile
  painting programs run through `run_painting_program`. It fails on any
  leak and also checks that normal work (own files, Grep, python, painting)
  still functions.
