"""SSM loading is per CODE_MONET_ENV; `none` means configuration comes from the environment."""

import sys
import types

import pytest

from code_monet import config


def test_none_never_calls_ssm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_MONET_ENV", "none")
    boom = types.ModuleType("boto3")

    def client(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("SSM must not be called")

    boom.client = client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", boom)
    config._get_ssm_params.cache_clear()
    try:
        assert config._get_ssm_params() == {}
    finally:
        config._get_ssm_params.cache_clear()
