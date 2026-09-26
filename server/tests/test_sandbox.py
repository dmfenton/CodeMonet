"""The sandbox for agent-written code: policy, launch spec, and (on Linux) enforcement."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from code_monet import claude_runtime, claude_sandbox, sandbox
from code_monet.claude_runtime import SANDBOXED_CLI, claude_launch
from code_monet.config import settings
from code_monet.paint_runner import paint_policy


class TestSeccompFilter:
    @pytest.mark.parametrize("arch", sorted(sandbox._ARCHES))
    @pytest.mark.parametrize("network", [True, False])
    @pytest.mark.parametrize("subprocesses", [True, False])
    def test_assembles_for_every_arch_and_policy(
        self, arch: str, network: bool, subprocesses: bool
    ) -> None:
        policy = sandbox.Policy((), (), network, subprocesses, (1, 4242))

        prog = sandbox._filter(policy, sandbox._ARCHES[arch])

        assert len(prog) % 8 == 0 and 0 < len(prog) // 8 < 4096
        # First: check the architecture, killing on mismatch.
        code, _, jf, k = struct.unpack_from("=HBBI", prog, 8)
        assert (code, k) == (sandbox._JEQ_K, sandbox._ARCHES[arch].audit) and jf == 0

    def test_protects_pids_their_groups_and_broadcast(self) -> None:
        targets = sandbox._protected_targets((1, 4242))

        assert set(targets) == {1, 0xFFFFFFFF, 4242, (-4242) & 0xFFFFFFFF}


class TestCliEnvironment:
    def test_keeps_only_sdk_variables_and_the_spec(self) -> None:
        inherited = {
            "JWT_SECRET": "server-secret",
            "AWS_SECRET_ACCESS_KEY": "aws",
            "ANTHROPIC_API_KEY": "stray",
            "HOME": "/home/appuser",
            "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
            "CLAUDE_AGENT_SDK_VERSION": "0.2",
            "PWD": "/ws",
            "CODE_MONET_SANDBOX": "{}",
        }

        env = claude_sandbox.cli_environment(inherited, {"HOME": "/users/u1", "PATH": "/bin"})

        assert env == {
            "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
            "CLAUDE_AGENT_SDK_VERSION": "0.2",
            "PWD": "/ws",
            "HOME": "/users/u1",
            "PATH": "/bin",
        }

    def test_refuses_to_run_without_a_launch_spec(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv(claude_sandbox.SPEC_ENV, raising=False)

        assert claude_sandbox.main(["-v"]) == 2
        assert "refusing" in capsys.readouterr().err

    def test_launcher_script_is_executable(self) -> None:
        assert os.access(SANDBOXED_CLI, os.X_OK)


def _spec(env: dict[str, str]) -> dict[str, object]:
    return dict(json.loads(env[claude_sandbox.SPEC_ENV]))


class TestClaudeLaunch:
    def test_workload_identity_gets_a_private_home_per_user(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        token = tmp_path / "secrets" / "aws-identity-token"
        token.parent.mkdir()
        token.write_text("header.payload.signature")
        monkeypatch.setattr(settings, "anthropic_federation_rule_id", "fdrl_test")
        monkeypatch.setattr(
            settings, "anthropic_organization_id", "00000000-0000-4000-8000-000000000000"
        )
        monkeypatch.setattr(settings, "anthropic_service_account_id", "svac_test")
        monkeypatch.setattr(settings, "anthropic_identity_token_file", str(token))
        monkeypatch.setattr(settings, "anthropic_config_directory", str(tmp_path / "config"))
        monkeypatch.setattr(claude_runtime, "real_cli", lambda: "/opt/sdk/_bundled/claude")
        monkeypatch.setenv("JWT_SECRET", "server-secret")

        launch = claude_launch("user-1", "/data/users/user-1")

        home = tmp_path / "config" / "users" / "user-1"
        spec = _spec(launch.env)
        env = spec["env"]
        assert isinstance(env, dict)
        assert launch.cli_path == str(SANDBOXED_CLI) and launch.cwd == "/data/users/user-1"
        assert set(launch.env) == {claude_sandbox.SPEC_ENV}
        assert spec["cli"] == "/opt/sdk/_bundled/claude"
        assert env["HOME"] == str(home) and env["TMPDIR"] == str(home / "tmp")
        assert env["CLAUDE_CONFIG_DIR"] == str(home / "claude")
        assert "JWT_SECRET" not in env
        assert spec["write"] == ["/data/users/user-1", str(home), "/dev"]
        assert str(token.parent) in spec["read"]  # type: ignore[operator]
        assert (home / "tmp").is_dir()

    def test_development_uses_the_developers_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "dev_mode", True)
        monkeypatch.setattr(settings, "anthropic_federation_rule_id", "")
        monkeypatch.setattr(settings, "anthropic_organization_id", "")
        monkeypatch.setattr(settings, "anthropic_service_account_id", "")
        monkeypatch.setattr(claude_runtime, "real_cli", lambda: "/opt/claude")
        monkeypatch.setenv("HOME", "/Users/dev")
        monkeypatch.setenv("JWT_SECRET", "server-secret")

        spec = _spec(claude_launch("user-1", "/ws").env)

        env = spec["env"]
        assert isinstance(env, dict)
        assert env["HOME"] == "/Users/dev" and "JWT_SECRET" not in env
        assert "CLAUDE_CONFIG_DIR" not in env
        assert spec["write"] == ["/ws", "/Users/dev", "/dev"]


class TestPaintPolicy:
    def test_writes_only_its_output_and_scratch_dirs(self) -> None:
        policy = paint_policy("/data/users/u/paintings/t", "/tmp/paint-run-x")

        assert policy.write == ("/data/users/u/paintings/t", "/tmp/paint-run-x")
        assert not policy.network and not policy.subprocesses
        assert sys.prefix in policy.read and os.getppid() in policy.protected_pids


# --- Enforcement (Linux with Landlock) -----------------------------------------

# Production requires Landlock, so on Linux these fail (not skip) without it.
linux_only = pytest.mark.skipif(not sandbox.available(), reason="Linux-only sandbox")

PROBE = textwrap.dedent(
    """
    import json, os, socket, sys
    from code_monet import sandbox
    root, max_abi, confine = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "confine"
    parent = os.getppid()
    if confine:
        sandbox.confine(sandbox.Policy(
            read=(sys.prefix, sys.base_prefix, "/usr", "/lib", "/proc"),
            write=(f"{root}/own",),
            network=False, subprocesses=False, protected_pids=(parent,),
        ), max_abi=max_abi or None)
    def fork():
        pid = os.fork()
        if pid == 0:
            os._exit(0)
        os.waitpid(pid, 0)
    def attempt(f):
        try:
            f()
            return "allowed"
        except OSError:
            return "denied"
    print(json.dumps({
        "write_own": attempt(lambda: open(f"{root}/own/x", "w").write("x")),
        "read_other": attempt(lambda: open(f"{root}/other/secret").read()),
        "list_other": attempt(lambda: os.listdir(f"{root}/other")),
        "parent_environ": attempt(lambda: open(f"/proc/{parent}/environ").read()),
        "truncate_other": attempt(lambda: os.truncate(f"{root}/other/secret", 0)),
        "chmod_other": attempt(lambda: os.chmod(f"{root}/other/secret", 0o600)),
        "rename_out": attempt(lambda: os.rename(f"{root}/own/x", f"{root}/x")),
        "signal_parent": attempt(lambda: os.kill(parent, 0)),
        "broadcast_signal": attempt(lambda: os.kill(-1, 0)),
        "inet_socket": attempt(lambda: socket.socket(socket.AF_INET).close()),
        "unix_socket": attempt(lambda: socket.socket(socket.AF_UNIX).close()),
        "fork": attempt(fork),
    }))
    """
)


def _probe(root: Path, max_abi: int, mode: str) -> dict[str, str]:
    (root / "own").mkdir()
    (root / "other").mkdir()
    (root / "other" / "secret").write_text("secret")
    out = subprocess.run(
        [sys.executable, "-c", PROBE, str(root), str(max_abi), mode],
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(json.loads(out.stdout.splitlines()[-1]))


@linux_only
class TestEnforcement:
    @pytest.mark.parametrize("max_abi", [0, 2])  # native, and production's kernel 6.1
    def test_confined_process_reaches_only_its_policy(self, tmp_path: Path, max_abi: int) -> None:
        seen = _probe(tmp_path, max_abi, "confine")

        assert {k for k, v in seen.items() if v == "allowed"} == {"write_own", "unix_socket"}, seen
        assert (tmp_path / "other" / "secret").read_text() == "secret"

    def test_the_probe_detects_access_when_unconfined(self, tmp_path: Path) -> None:
        seen = _probe(tmp_path, 0, "none")

        assert {k for k, v in seen.items() if v == "denied"} <= {"parent_environ"}, seen
