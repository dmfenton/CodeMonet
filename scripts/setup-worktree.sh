#!/bin/bash
# Setup symlinks and dependencies for a worktree
# Run from worktree root OR pass worktree path as argument
set -e

WORKTREE="${1:-$(pwd)}"
cd "$WORKTREE"

# Find the main repository
MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')

if [ -z "$MAIN_REPO" ] || [ "$MAIN_REPO" = "$WORKTREE" ]; then
    echo "Error: Not in a worktree or main repo not found"
    exit 1
fi

echo "Worktree: $WORKTREE"
echo "Main repo: $MAIN_REPO"
echo ""

# Symlink .env
if [ -f "${MAIN_REPO}/.env" ] && [ ! -e .env ]; then
    ln -s "${MAIN_REPO}/.env" .env
    echo "✓ Symlinked .env"
elif [ -L .env ]; then
    echo "✓ .env already symlinked"
elif [ -f .env ]; then
    echo "⚠ .env exists (not symlinked)"
else
    echo "⚠ No .env in main repo"
fi

# Symlink server/data (SQLite DB)
mkdir -p server
if [ -d "${MAIN_REPO}/server/data" ] && [ ! -e server/data ]; then
    ln -s "${MAIN_REPO}/server/data" server/data
    echo "✓ Symlinked server/data"
elif [ -L server/data ]; then
    echo "✓ server/data already symlinked"
elif [ -d server/data ]; then
    echo "⚠ server/data exists (not symlinked)"
else
    # Create empty data dir in main if missing
    mkdir -p "${MAIN_REPO}/server/data"
    ln -s "${MAIN_REPO}/server/data" server/data
    echo "✓ Created and symlinked server/data"
fi

# Symlink agent_workspace
if [ -d "${MAIN_REPO}/agent_workspace" ] && [ ! -e agent_workspace ]; then
    ln -s "${MAIN_REPO}/agent_workspace" agent_workspace
    echo "✓ Symlinked agent_workspace"
elif [ -L agent_workspace ]; then
    echo "✓ agent_workspace already symlinked"
elif [ -d agent_workspace ]; then
    echo "⚠ agent_workspace exists (not symlinked)"
else
    echo "⚠ No agent_workspace in main repo (will be created on first use)"
fi

# Optional: symlink node_modules to save disk/install time
# Uncomment if you want shared node_modules (can cause issues with different branches)
# if [ -d "${MAIN_REPO}/node_modules" ] && [ ! -e node_modules ]; then
#     ln -s "${MAIN_REPO}/node_modules" node_modules
#     echo "✓ Symlinked node_modules"
# fi

echo ""
echo "Setup complete!"
echo ""

# Check what still needs to be done
NEEDS_INSTALL=false
if [ ! -d server/.venv ]; then
    echo "Run: cd server && uv sync --all-extras"
    NEEDS_INSTALL=true
fi
if [ ! -d node_modules ]; then
    echo "Run: npm install"
    NEEDS_INSTALL=true
fi

if [ "$NEEDS_INSTALL" = false ]; then
    echo "Dependencies appear to be installed."
fi
