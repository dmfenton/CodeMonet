---
name: "source-command-setup-worktree"
description: "Setup symlinks for current worktree (env, db, workspace)"
---

# source-command-setup-worktree

Use this skill when the user asks to run the migrated source command `setup-worktree`.

## Command Template

Run the setup script to symlink shared resources from the main repo:

```bash
./scripts/setup-worktree.sh
```

This creates symlinks for:

- `.env` → main repo's environment config
- `server/data/` → main repo's SQLite database
- `agent_workspace/` → main repo's workspace directory

After setup, install dependencies if needed:

```bash
cd server && uv sync --all-extras
npm install --legacy-peer-deps
```
