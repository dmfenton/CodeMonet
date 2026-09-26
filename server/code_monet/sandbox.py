"""Confine the current process before it runs agent-written code.

Agent-written code (painting programs, the agent's shell and file tools) runs as
the server's OS user in the server's container. `confine` narrows what this
process and everything it later execs can do, with two unprivileged kernel
mechanisms (no namespaces, so the container's seccomp profile is unchanged):

- Landlock: filesystem access only below the policy's read and write roots.
  It also blocks ptrace (and so /proc/<pid>/environ, mem, fd) of processes
  outside the sandbox, such as the server.
- seccomp: denies what Landlock does not cover on older kernels (path-based
  chmod/chown/truncate, signals to the server), io_uring, and optionally
  network sockets and new processes.

Linux only; the caller decides what to do elsewhere (`available`). Standard
library only: the paint runner imports this before anything else.
"""

from __future__ import annotations

import ctypes
import os
import platform
import stat
import struct
import sys
import threading
from dataclasses import dataclass, field

_MIN_LANDLOCK_ABI = 2  # REFER: without it cross-directory renames are unrestricted


class SandboxError(RuntimeError):
    """The sandbox could not be applied; the caller must not run untrusted code."""


@dataclass(frozen=True)
class Policy:
    read: tuple[str, ...]  # read and execute below these paths
    write: tuple[str, ...]  # full access below these paths
    network: bool = True  # False: only AF_UNIX sockets
    subprocesses: bool = True  # False: no fork/exec (threads are fine)
    protected_pids: tuple[int, ...] = field(default_factory=tuple)  # never signalled


def python_policy(*write: str) -> Policy:
    """Untrusted Python: read Python, its packages and shared libraries; write only
    `write`; no network, no new processes, no signals to the parent or PID 1."""
    python = {sys.prefix, sys.base_prefix, sys.exec_prefix, *filter(os.path.isdir, sys.path)}
    return Policy(
        read=(*sorted(python), "/lib", "/usr/lib"),
        write=write,
        network=False,
        subprocesses=False,
        protected_pids=(1, os.getppid()),
    )


def available() -> bool:
    return sys.platform == "linux" and platform.machine() in _ARCHES


def confine(policy: Policy, *, max_abi: int | None = None) -> int:
    """Apply `policy` to this process for good; returns the Landlock ABI used.

    Must run while the process is single-threaded: Landlock and seccomp apply
    to the calling thread and the threads and processes it creates later.
    """
    if not available():
        raise SandboxError(f"sandbox unsupported on {sys.platform}/{platform.machine()}")
    if threading.active_count() != 1:
        raise SandboxError("confine() must run before any threads start")
    abi = _landlock_abi()
    if max_abi is not None:
        abi = min(abi, max_abi)
    if abi < _MIN_LANDLOCK_ABI:
        raise SandboxError(f"Landlock ABI {abi} < {_MIN_LANDLOCK_ABI}")
    _own_session()
    _prctl(_PR_SET_NO_NEW_PRIVS, 1)
    _landlock(policy, abi)
    _seccomp(policy)
    return abi


def _own_session() -> None:
    """Leave the parent's session and process group, so kill(0) reaches only us."""
    if os.getsid(0) != os.getpid():
        os.setsid()


# --- Landlock ------------------------------------------------------------------

_SYS_LANDLOCK_CREATE_RULESET = 444  # same number on x86_64 and aarch64
_SYS_LANDLOCK_ADD_RULE = 445
_SYS_LANDLOCK_RESTRICT_SELF = 446
_LANDLOCK_CREATE_RULESET_VERSION = 1
_LANDLOCK_RULE_PATH_BENEATH = 1

_FS_EXECUTE = 1 << 0
_FS_WRITE_FILE = 1 << 1
_FS_READ_FILE = 1 << 2
_FS_READ_DIR = 1 << 3
_FS_REFER = 1 << 13  # ABI 2
_FS_TRUNCATE = 1 << 14  # ABI 3
_FS_IOCTL_DEV = 1 << 15  # ABI 5
_FS_FILE_ONLY = _FS_EXECUTE | _FS_WRITE_FILE | _FS_READ_FILE | _FS_TRUNCATE | _FS_IOCTL_DEV
_SCOPE_ABSTRACT_UNIX_SOCKET = 1 << 0  # ABI 6
_SCOPE_SIGNAL = 1 << 1  # ABI 6

_O_PATH = getattr(os, "O_PATH", 0)  # Linux only; typeshed hides it elsewhere

_libc = ctypes.CDLL(None, use_errno=True)
_libc.syscall.restype = ctypes.c_long


def _syscall(nr: int, *args: int | ctypes.c_void_p | bytes | None) -> int:
    ret = int(_libc.syscall(ctypes.c_long(nr), *args))
    if ret < 0:
        err = ctypes.get_errno()
        raise SandboxError(f"syscall {nr} failed: {os.strerror(err)}")
    return ret


def _landlock_abi() -> int:
    try:
        return _syscall(_SYS_LANDLOCK_CREATE_RULESET, None, 0, _LANDLOCK_CREATE_RULESET_VERSION)
    except SandboxError:
        return 0


def _handled_fs(abi: int) -> int:
    rights = (1 << 13) - 1  # ABI 1: EXECUTE .. MAKE_SYM
    if abi >= 2:
        rights |= _FS_REFER
    if abi >= 3:
        rights |= _FS_TRUNCATE
    if abi >= 5:
        rights |= _FS_IOCTL_DEV
    return rights


def _landlock(policy: Policy, abi: int) -> None:
    handled = _handled_fs(abi)
    scoped = _SCOPE_ABSTRACT_UNIX_SOCKET | _SCOPE_SIGNAL if abi >= 6 else 0
    # struct landlock_ruleset_attr { u64 handled_access_fs, handled_access_net, scoped }
    attr = struct.pack("=QQQ", handled, 0, scoped) if abi >= 6 else struct.pack("=Q", handled)
    ruleset = _syscall(_SYS_LANDLOCK_CREATE_RULESET, attr, len(attr), 0)
    try:
        read = _FS_EXECUTE | _FS_READ_FILE | _FS_READ_DIR
        for path in policy.read:
            _allow(ruleset, path, read & handled)
        for path in policy.write:
            _allow(ruleset, path, handled)
        _syscall(_SYS_LANDLOCK_RESTRICT_SELF, ruleset, 0)
    finally:
        os.close(ruleset)


def _allow(ruleset: int, path: str, rights: int) -> None:
    try:
        fd = os.open(path, _O_PATH | os.O_CLOEXEC)
    except FileNotFoundError:
        return
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            rights &= _FS_FILE_ONLY
        # struct landlock_path_beneath_attr { u64 allowed_access; s32 parent_fd } (packed)
        rule = struct.pack("=Qi", rights, fd)
        _syscall(_SYS_LANDLOCK_ADD_RULE, ruleset, _LANDLOCK_RULE_PATH_BENEATH, rule, 0)
    finally:
        os.close(fd)


# --- seccomp -------------------------------------------------------------------

_PR_SET_NO_NEW_PRIVS = 38
_PR_SET_SECCOMP = 22
_SECCOMP_MODE_FILTER = 2
_RET_ALLOW = 0x7FFF0000
_RET_ERRNO = 0x00050000
_RET_KILL_PROCESS = 0x80000000
_EPERM = 1
_ENOSYS = 38
_AF_UNIX = 1
_CLONE_THREAD = 0x10000
_X32_BIT = 0x40000000


@dataclass(frozen=True)
class _Arch:
    audit: int
    nr: dict[str, int]


# Absent names (e.g. chmod on aarch64) do not exist on that architecture.
_ARCHES = {
    "x86_64": _Arch(
        0xC000003E,
        {
            "chmod": 90, "fchmodat": 268, "fchmodat2": 452, "chown": 92, "lchown": 94,
            "fchownat": 260, "truncate": 76, "io_uring_setup": 425, "kill": 62,
            "tkill": 200, "tgkill": 234, "rt_sigqueueinfo": 129, "rt_tgsigqueueinfo": 297,
            "pidfd_open": 434, "pidfd_send_signal": 424, "socket": 41, "fork": 57, "vfork": 58, "clone": 56,
            "clone3": 435, "execve": 59, "execveat": 322,
        },
    ),
    "aarch64": _Arch(
        0xC00000B7,
        {
            "fchmodat": 53, "fchmodat2": 452, "fchownat": 54, "truncate": 45,
            "io_uring_setup": 425, "kill": 129, "tkill": 130, "tgkill": 131,
            "rt_sigqueueinfo": 138, "rt_tgsigqueueinfo": 240, "pidfd_open": 434,
            "pidfd_send_signal": 424,
            "socket": 198, "clone": 220, "clone3": 435, "execve": 221, "execveat": 281,
        },
    ),
}  # fmt: skip

# Path-based mutations Landlock ABI 2 does not govern. The fd-based ones
# (fchmod, ftruncate, fsetxattr, futimens) need a writable or owned fd, which
# Landlock (opens) and file ownership already limit to the sandbox's own files.
# pidfd_send_signal: pidfds of protected processes are also unobtainable
# (pidfd_open is pid-checked below), but deny it outright.
_ALWAYS_DENIED = (
    "chmod", "fchmodat", "fchmodat2", "chown", "lchown", "fchownat", "truncate",
    "io_uring_setup", "tkill", "pidfd_send_signal",
)  # fmt: skip
_TARGETS_PID = ("kill", "tgkill", "rt_sigqueueinfo", "rt_tgsigqueueinfo", "pidfd_open")

# BPF opcodes
_LD_W_ABS = 0x20
_JEQ_K = 0x15
_JGE_K = 0x35
_JSET_K = 0x45
_RET_K = 0x06
_NR, _ARCH_OFF, _ARG0_LO = 0, 4, 16  # struct seccomp_data offsets (little-endian)


class _Asm:
    """Tiny BPF assembler: straight-line blocks ending in returns, forward jumps."""

    def __init__(self) -> None:
        self.ops: list[tuple[int, int | str, int | str, int]] = []
        self.labels: dict[str, int] = {}

    def op(self, code: int, k: int, jt: int | str = 0, jf: int | str = 0) -> None:
        self.ops.append((code, jt, jf, k))

    def label(self, name: str) -> None:
        self.labels[name] = len(self.ops)

    def assemble(self) -> bytes:
        out = b""
        for i, (code, jt, jf, k) in enumerate(self.ops):
            t = self.labels[jt] - i - 1 if isinstance(jt, str) else jt
            f = self.labels[jf] - i - 1 if isinstance(jf, str) else jf
            if not (0 <= t < 256 and 0 <= f < 256):
                raise SandboxError("seccomp filter jump out of range")
            out += struct.pack("=HBBI", code, t, f, k & 0xFFFFFFFF)
        return out


def _filter(policy: Policy, arch: _Arch) -> bytes:
    a = _Asm()
    nr = arch.nr
    a.op(_LD_W_ABS, _ARCH_OFF)
    a.op(_JEQ_K, arch.audit, 1, 0)
    a.op(_RET_K, _RET_KILL_PROCESS)
    a.op(_LD_W_ABS, _NR)
    if arch.audit == _ARCHES["x86_64"].audit:
        a.op(_JGE_K, _X32_BIT, "deny", 0)  # x32 ABI aliases
    for name in _ALWAYS_DENIED:
        if name in nr:
            a.op(_JEQ_K, nr[name], "deny", 0)
    for name in _TARGETS_PID:
        a.op(_JEQ_K, nr[name], "pid_check", 0)
    if not policy.network:
        a.op(_JEQ_K, nr["socket"], "socket_check", 0)
    if not policy.subprocesses:
        for name in ("fork", "vfork", "execve", "execveat"):
            if name in nr:
                a.op(_JEQ_K, nr[name], "deny", 0)
        a.op(_JEQ_K, nr["clone3"], "enosys", 0)  # libc falls back to clone
        a.op(_JEQ_K, nr["clone"], "clone_check", 0)
    a.op(_RET_K, _RET_ALLOW)

    a.label("pid_check")
    a.op(_LD_W_ABS, _ARG0_LO)
    for pid in _protected_targets(policy.protected_pids):
        a.op(_JEQ_K, pid, "deny", 0)
    a.op(_RET_K, _RET_ALLOW)

    if not policy.network:
        a.label("socket_check")
        a.op(_LD_W_ABS, _ARG0_LO)
        a.op(_JEQ_K, _AF_UNIX, 0, "deny")
        a.op(_RET_K, _RET_ALLOW)

    if not policy.subprocesses:
        a.label("clone_check")
        a.op(_LD_W_ABS, _ARG0_LO)
        a.op(_JSET_K, _CLONE_THREAD, 0, "deny")
        a.op(_RET_K, _RET_ALLOW)
        a.label("enosys")
        a.op(_RET_K, _RET_ERRNO | _ENOSYS)

    a.label("deny")
    a.op(_RET_K, _RET_ERRNO | _EPERM)
    return a.assemble()


def _protected_targets(pids: tuple[int, ...]) -> list[int]:
    """Signal targets to refuse: each pid and its process group, plus broadcast (-1)."""
    targets = {0xFFFFFFFF}
    for pid in pids:
        targets |= {pid & 0xFFFFFFFF, -pid & 0xFFFFFFFF}
    return sorted(targets)


def _seccomp(policy: Policy) -> None:
    prog = _filter(policy, _ARCHES[platform.machine()])
    buf = ctypes.create_string_buffer(prog)
    # struct sock_fprog { unsigned short len; struct sock_filter *filter; }
    fprog = struct.pack("@HP", len(prog) // 8, ctypes.addressof(buf))
    _prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, fprog)


def _prctl(option: int, arg2: int, arg3: bytes | int = 0) -> None:
    zero = ctypes.c_ulong(0)
    if _libc.prctl(ctypes.c_int(option), ctypes.c_ulong(arg2), arg3, zero, zero) != 0:
        err = ctypes.get_errno()
        raise SandboxError(f"prctl({option}) failed: {os.strerror(err)}")
