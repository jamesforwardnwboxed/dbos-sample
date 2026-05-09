from __future__ import annotations

import pytest

from control_plane.config import load_config


def test_load_config_defaults_to_quiet_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONTROL_PLANE_LOG_LEVEL", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_ACCESS_LOG", raising=False)

    config = load_config()

    assert config.log_level == "info"
    assert config.access_log is False


def test_load_config_reads_logging_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROL_PLANE_LOG_LEVEL", "INFO")
    monkeypatch.setenv("CONTROL_PLANE_ACCESS_LOG", "true")

    config = load_config()

    assert config.log_level == "info"
    assert config.access_log is True
