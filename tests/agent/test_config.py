import pytest
from pathlib import Path
from agent.service.config import load_config, Config

FIXTURE_CONFIG = Path(__file__).parent.parent.parent / "config" / "config.yaml"


def test_load_config_returns_config_object():
    cfg = load_config(FIXTURE_CONFIG)
    assert isinstance(cfg, Config)


def test_load_config_emr_modules_loaded():
    cfg = load_config(FIXTURE_CONFIG)
    assert "accuro" in cfg.emr_modules
    assert "patient_search" in cfg.emr_modules["accuro"]
    assert isinstance(cfg.emr_modules["accuro"]["patient_search"], list)


def test_load_config_emr_processes_loaded():
    cfg = load_config(FIXTURE_CONFIG)
    assert "ps_suite" in cfg.emr_processes
    assert "PSS.exe" in cfg.emr_processes["ps_suite"]["process_names"]


def test_load_config_poll_interval():
    cfg = load_config(FIXTURE_CONFIG)
    assert cfg.poll_interval == 0.2


def test_load_config_idle_timeout():
    cfg = load_config(FIXTURE_CONFIG)
    assert cfg.idle_timeout == 900
