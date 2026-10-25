# Database & Storage

## Architecture

- **SQLite** (via SQLAlchemy async): Auth only (users, invite codes)
- **Filesystem**: Per-user workspace data

## Database Location

- Dev: `server/data/code_monet.db`
- Prod (container): `/app/data/drawing_agent.db`
- Prod (host): `/home/ec2-user/data/codemonet/drawing_agent.db` (on EBS volume)

## Migrations

```bash
# Create new migration
uv run alembic revision -m "description"

# Run migrations
uv run alembic upgrade head

# Check current version
uv run alembic current
```

## Workspace Storage

Each user has a filesystem directory:

```
agent_workspace/users/{user_id}/
├── workspace.json       # Canvas state, notes, piece_count
└── gallery/
    └── piece_000001.json  # Saved artwork
```

## CLI Commands

```bash
# Invite code management
uv run python -m code_monet.cli invite create      # Create invite code
uv run python -m code_monet.cli invite create -c 5 # Create 5 codes
uv run python -m code_monet.cli invite list        # List all invite codes
uv run python -m code_monet.cli invite revoke CODE # Revoke unused code

# User management
uv run python -m code_monet.cli user list          # List users with workspace summary
uv run python -m code_monet.cli user list --all    # Include inactive users
uv run python -m code_monet.cli user workspace 1   # Show workspace details for user ID 1

# Workspace filesystem
uv run python -m code_monet.cli workspace list     # List all workspace directories
```

## Creating Users Directly

To create a user without an invite code (e.g., admin):

```python
# Run from server/ directory
uv run python -c "
import asyncio
from code_monet.db import get_session, repository
from code_monet.auth.password import hash_password

async def create_user(email: str, password: str):
    async with get_session() as session:
        existing = await repository.get_user_by_email(session, email)
        if existing:
            print(f'User already exists: id={existing.id}')
            return
        user = await repository.create_user(session, email, hash_password(password))
        print(f'Created user: {email} (id={user.id})')

asyncio.run(create_user('admin@example.com', 'ChangeMe123!'))
"
```
