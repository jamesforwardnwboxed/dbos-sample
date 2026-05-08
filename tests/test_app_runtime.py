from __future__ import annotations

import logging

import pytest

import app_runtime


def test_build_dbos_config_reads_conductor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DBOS_APP_NAME", "custom-app")
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "postgres://postgres:dbos@postgres:5432/dbos_starter")
    monkeypatch.setenv("DBOS_CONDUCTOR_URL", "ws://control-plane:8001")
    monkeypatch.setenv("DBOS_CONDUCTOR_KEY", "test-key")

    config = app_runtime.build_dbos_config()

    assert config["name"] == "custom-app"
    assert config["system_database_url"] == "postgres://postgres:dbos@postgres:5432/dbos_starter"
    assert config["conductor_url"] == "ws://control-plane:8001"
    assert config["conductor_key"] == "test-key"


def test_run_workflow_logic_exits_once_when_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(app_runtime, "step_one", lambda name: len(name))
    monkeypatch.setattr(app_runtime, "step_two", lambda name, name_length: events.append((name, name_length)))
    monkeypatch.setattr(app_runtime, "get_existing_file_path", lambda: str(tmp_path / "existing.txt"))

    def fake_exit(code: int) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(app_runtime.os, "_exit", fake_exit)

    with pytest.raises(SystemExit) as exc_info:
        app_runtime.run_workflow_logic("world")

    assert exc_info.value.code == 1
    assert (tmp_path / "existing.txt").exists()
    assert events == []


def test_run_workflow_logic_completes_when_file_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    events: list[tuple[str, int]] = []
    existing_file = tmp_path / "existing.txt"
    existing_file.touch()

    monkeypatch.setattr(app_runtime, "step_one", lambda name: len(name))
    monkeypatch.setattr(app_runtime, "step_two", lambda name, name_length: events.append((name, name_length)))
    monkeypatch.setattr(app_runtime, "get_existing_file_path", lambda: str(existing_file))

    app_runtime.run_workflow_logic("James")

    assert events == [("James", 5)]


def test_configure_logging_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_LOG_LEVEL", raising=False)

    app_runtime.configure_logging()

    assert logging.getLogger().getEffectiveLevel() == logging.INFO


def test_configure_logging_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_LOG_LEVEL", "debug")

    app_runtime.configure_logging()

    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
