"""Keep unit tests hermetic: CI has neither the repo .env nor AWS credentials.

Without this, a local run silently reads secrets (e.g. JWT_SECRET) from ../.env or
the dev SSM path and passes tests that fail in CI. Explicit environments (the
e2e targets set CODE_MONET_ENV=prod) keep their real configuration.
"""

import os

if "CODE_MONET_ENV" not in os.environ:
    os.environ["CODE_MONET_ENV"] = "unit-test"  # no SSM parameters live under this path
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"

    from code_monet.config import Settings, settings

    _without_env_files = Settings(_env_file=None)  # type: ignore[call-arg]
    for _name in Settings.model_fields:
        setattr(settings, _name, getattr(_without_env_files, _name))
