#!/usr/bin/env python3
"""Sync production database and workspace to local dev environment.

Handles the SSM 24KB output limit by automatically chunking file transfers
via base64-encoded segments.

Usage:
    uv run python scripts/sync-prod.py           # Full sync (DB + workspace)
    uv run python scripts/sync-prod.py --db-only  # Just the database
    uv run python scripts/sync-prod.py --ws-only   # Just the workspace
"""

import base64
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import shlex

# Reuse remote.py's SSM infrastructure
sys.path.insert(0, os.path.dirname(__file__))
from remote import run_command

# Configuration
REMOTE_DB_PATH = "/home/ec2-user/data/codemonet/drawing_agent.db"
REMOTE_WORKSPACE_BASE = "/home/ec2-user/data/codemonet/agent_workspace/users"
LOCAL_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "server", "data")
LOCAL_DB_PATH = os.path.join(LOCAL_DATA_DIR, "code_monet.db")
LOCAL_WORKSPACE_DIR = os.path.join(LOCAL_DATA_DIR, "agent_workspace", "users")
TARGET_EMAIL = "dmfenton@gmail.com"

# SSM output caps at ~24000 bytes. Base64 of 17000 raw bytes = ~22668 bytes.
CHUNK_SIZE = 17000


def print_step(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def get_remote_file_size(path: str) -> int:
    """Get size of a file on the remote host."""
    code, stdout, stderr = run_command(f"stat -c%s {path}", timeout=10)
    if code != 0:
        raise RuntimeError(f"Failed to get file size for {path}: {stderr}")
    return int(stdout.strip())


def download_chunked(remote_path: str, local_path: str):
    """Download a remote file via SSM using base64 chunking."""
    file_size = get_remote_file_size(remote_path)
    num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"  File size: {file_size:,} bytes -> {num_chunks} chunks")

    raw_data = bytearray()
    for i in range(num_chunks):
        offset = i * CHUNK_SIZE
        count = min(CHUNK_SIZE, file_size - offset)
        print(f"  Downloading chunk {i+1}/{num_chunks} (offset={offset}, size={count})...", end=" ", flush=True)

        cmd = f"tail -c +{offset + 1} {shlex.quote(remote_path)} | head -c {count} | base64"
        code, stdout, stderr = run_command(cmd, timeout=60)
        if code != 0:
            raise RuntimeError(f"Failed to download chunk {i+1}: {stderr}")

        chunk_b64 = stdout.strip()
        chunk_bytes = base64.b64decode(chunk_b64)
        raw_data.extend(chunk_bytes)
        print(f"OK ({len(chunk_bytes)} bytes)")

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(raw_data)

    print(f"  Written {len(raw_data):,} bytes to {local_path}")
    if len(raw_data) != file_size:
        raise RuntimeError(f"Size mismatch: expected {file_size} bytes but got {len(raw_data)}")


def sync_database():
    """Download production database with backup."""
    print_step("Syncing production database")

    # Backup existing
    if os.path.exists(LOCAL_DB_PATH):
        backup_path = LOCAL_DB_PATH + ".bak"
        shutil.copy2(LOCAL_DB_PATH, backup_path)
        print(f"  Backed up existing DB to {backup_path}")

    download_chunked(REMOTE_DB_PATH, LOCAL_DB_PATH)

    # Verify
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.execute("SELECT count(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    print(f"  Verified: {count} users in database")


def get_user_id() -> str:
    """Get user ID for target email from local database."""
    conn = sqlite3.connect(LOCAL_DB_PATH)
    cursor = conn.execute("SELECT id FROM users WHERE email=?", (TARGET_EMAIL,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise RuntimeError(f"User {TARGET_EMAIL} not found in database")
    user_id = str(row[0])
    print(f"  User ID for {TARGET_EMAIL}: {user_id}")
    return user_id


def sync_workspace(user_id: str):
    """Download user workspace via tar + chunked transfer."""
    print_step(f"Syncing workspace for user {user_id}")

    # Create tar on remote, get its size
    remote_tar = f"/tmp/workspace-{user_id}.tar.gz"
    print("  Creating tarball on remote...")
    code, stdout, stderr = run_command(
        f"tar -czf {shlex.quote(remote_tar)} -C {shlex.quote(REMOTE_WORKSPACE_BASE)} {shlex.quote(user_id)} && stat -c%s {shlex.quote(remote_tar)}",
        timeout=120,
    )
    if code != 0:
        raise RuntimeError(f"Failed to create remote tarball: {stderr}")
    tar_size = int(stdout.strip())
    print(f"  Remote tarball: {tar_size:,} bytes")

    # Download the tarball
    local_tar = os.path.join(tempfile.gettempdir(), f"workspace-{user_id}.tar.gz")
    try:
        download_chunked(remote_tar, local_tar)
    finally:
        run_command(f"rm -f {shlex.quote(remote_tar)}", timeout=10)

    # Extract locally
    os.makedirs(LOCAL_WORKSPACE_DIR, exist_ok=True)

    # Remove existing workspace for this user
    local_user_dir = os.path.join(LOCAL_WORKSPACE_DIR, user_id)
    if os.path.exists(local_user_dir):
        shutil.rmtree(local_user_dir)
        print(f"  Removed existing workspace at {local_user_dir}")

    print("  Extracting tarball...")
    subprocess.run(
        ["tar", "-xzf", local_tar, "-C", LOCAL_WORKSPACE_DIR],
        check=True,
    )
    os.remove(local_tar)

    # Verify
    if os.path.isdir(local_user_dir):
        file_count = sum(len(files) for _, _, files in os.walk(local_user_dir))
        print(f"  Extracted workspace: {file_count} files")
        gallery_dir = os.path.join(local_user_dir, "gallery")
        if os.path.isdir(gallery_dir):
            pieces = len(os.listdir(gallery_dir))
            print(f"  Gallery pieces: {pieces}")
    else:
        print(f"  WARNING: Expected directory {local_user_dir} not found after extraction")


def verify():
    """Print summary of synced data."""
    print_step("Verification")

    conn = sqlite3.connect(LOCAL_DB_PATH)
    rows = conn.execute("SELECT id, email FROM users").fetchall()
    conn.close()
    print("  Database users:")
    for row in rows:
        print(f"    {row[0]}: {row[1]}")

    if os.path.isdir(LOCAL_WORKSPACE_DIR):
        for user_dir in os.listdir(LOCAL_WORKSPACE_DIR):
            full_path = os.path.join(LOCAL_WORKSPACE_DIR, user_dir)
            if os.path.isdir(full_path):
                file_count = sum(len(files) for _, _, files in os.walk(full_path))
                print(f"  Workspace {user_dir}: {file_count} files")

    print("\n  Sync complete!")


def main():
    sync_db = "--ws-only" not in sys.argv
    sync_ws = "--db-only" not in sys.argv

    if sync_db:
        sync_database()

    if sync_ws:
        if not sync_db and not os.path.exists(LOCAL_DB_PATH):
            print("ERROR: Local database not found. Run without --ws-only first.")
            sys.exit(1)
        user_id = get_user_id()
        sync_workspace(user_id)

    verify()


if __name__ == "__main__":
    main()
