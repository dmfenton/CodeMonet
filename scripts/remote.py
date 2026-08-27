#!/usr/bin/env python3
"""Server management script using AWS SSM.

Usage:
    python scripts/remote.py migrate           # Run database migrations
    python scripts/remote.py logs              # Tail container logs
    python scripts/remote.py restart           # Restart the container
    python scripts/remote.py exec "command"    # Run command in container
    python scripts/remote.py shell "command"   # Run command on host
    python scripts/remote.py create-user EMAIL PASSWORD  # Create admin user
    python scripts/remote.py create-invite     # Create invite code
"""

import sys
import time
from functools import lru_cache

import boto3

# Configuration
REGION = "us-east-1"
CONTAINER = "drawing-agent"


@lru_cache(maxsize=1)
def get_instance_id() -> str:
    """Fetch EC2 instance ID by Name tag (drawing-agent)."""
    ec2 = boto3.client("ec2", region_name=REGION)
    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": ["drawing-agent"]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            return instance["InstanceId"]
    raise RuntimeError("No running instance found with Name=drawing-agent")


def get_ssm_client():
    return boto3.client("ssm", region_name=REGION)


def run_command(command: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command on the EC2 instance via SSM."""
    ssm = get_ssm_client()
    instance_id = get_instance_id()

    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [command]},
        TimeoutSeconds=timeout,
    )

    command_id = response["Command"]["CommandId"]

    # Wait for completion
    for _ in range(timeout):
        time.sleep(1)
        try:
            result = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id,
            )
            if result["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
                return (
                    result["ResponseCode"],
                    result["StandardOutputContent"],
                    result["StandardErrorContent"],
                )
        except ssm.exceptions.InvocationDoesNotExist:
            continue

    return -1, "", "Command timed out"


def docker_exec(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command inside the Docker container."""
    return run_command(f"docker exec {CONTAINER} {cmd}", timeout)


def migrate():
    """Run database migrations."""
    print("Running migrations...")
    code, stdout, stderr = docker_exec(
        "/app/server/.venv/bin/python -m alembic upgrade head", timeout=60
    )
    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return code


def logs(lines: int = 100):
    """Get recent container logs."""
    code, stdout, stderr = run_command(f"docker logs --tail {lines} {CONTAINER}")
    print(stdout)
    if stderr:
        print(stderr)
    return code


def restart():
    """Restart the container."""
    print("Restarting container...")
    code, stdout, stderr = run_command(f"docker restart {CONTAINER}", timeout=60)
    print(stdout or "Container restarted")
    if stderr:
        print(stderr, file=sys.stderr)
    return code


def create_user(email: str, password: str):
    """Create a user directly in the database."""
    script = f'''
import asyncio
from drawing_agent.db import get_session, repository
from drawing_agent.auth.password import hash_password

async def create():
    async with get_session() as session:
        existing = await repository.get_user_by_email(session, "{email}")
        if existing:
            print(f"User already exists: id={{existing.id}}")
            return
        user = await repository.create_user(session, "{email}", hash_password("{password}"))
        print(f"Created user: {{user.email}} (id={{user.id}})")

asyncio.run(create())
'''
    print(f"Creating user: {email}")
    code, stdout, stderr = docker_exec(f"uv run python -c '{script}'", timeout=120)
    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    if code == 0:
        print(f"Password: {password}")
    return code


def create_invite():
    """Create an invite code."""
    print("Creating invite code...")
    code, stdout, stderr = docker_exec(
        "uv run python -m drawing_agent.cli invite create"
    )
    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return code


def exec_cmd(command: str):
    """Run arbitrary command in container."""
    code, stdout, stderr = docker_exec(command, timeout=60)
    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return code


def shell_cmd(command: str):
    """Run arbitrary command on the host (not in container)."""
    code, stdout, stderr = run_command(command, timeout=180)
    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return code


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "migrate":
        sys.exit(migrate())
    elif cmd == "logs":
        lines = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        sys.exit(logs(lines))
    elif cmd == "restart":
        sys.exit(restart())
    elif cmd == "create-user":
        if len(sys.argv) < 4:
            print("Usage: remote.py create-user EMAIL PASSWORD")
            sys.exit(1)
        email = sys.argv[2]
        password = sys.argv[3]
        sys.exit(create_user(email, password))
    elif cmd == "create-invite":
        sys.exit(create_invite())
    elif cmd == "exec":
        if len(sys.argv) < 3:
            print("Usage: remote.py exec 'command'")
            sys.exit(1)
        sys.exit(exec_cmd(" ".join(sys.argv[2:])))
    elif cmd == "shell":
        if len(sys.argv) < 3:
            print("Usage: remote.py shell 'command'")
            sys.exit(1)
        sys.exit(shell_cmd(" ".join(sys.argv[2:])))
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
