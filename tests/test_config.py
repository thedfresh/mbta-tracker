from __future__ import annotations

import textwrap

import pytest

from src.config import AppConfig, load_config


VALID_YAML = """
mbta:
  route_id: "109"
  stop_id: "5522"
  terminal_stop_id: "7412"
  poll_interval_seconds: 10

display:
  width: 128
  height: 64
  brightness: 80
  scroll_speed_fps: 20

logging:
  level: "INFO"
  log_dir: "logs/"
"""


def _write_yaml(tmp_path, contents: str) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent(contents))
    return str(path)


def test_load_config_valid(tmp_path, monkeypatch) -> None:
    path = _write_yaml(tmp_path, VALID_YAML)

    monkeypatch.setenv("MBTA_API_KEY", "testkey")
    config = load_config(path)

    assert isinstance(config, AppConfig)
    assert config.mbta.api_key == "testkey"
    assert config.mbta.route_id == "109"
    assert config.mbta.terminal_stop_id == "7412"
    assert config.display.width == 128
    assert config.log.level == "INFO"


def test_load_config_missing_file(tmp_path) -> None:
    missing_path = tmp_path / "does_not_exist.yaml"

    with pytest.raises(ValueError):
        load_config(str(missing_path))


def test_load_config_missing_mbta_key(tmp_path) -> None:
    yaml_text = """
    display:
      width: 128
      height: 64
      brightness: 80
      scroll_speed_fps: 20
    logging:
      level: "INFO"
      log_dir: "logs/"
    """
    path = _write_yaml(tmp_path, yaml_text)

    with pytest.raises(ValueError):
        load_config(path)


def test_load_config_missing_stop_id(tmp_path) -> None:
    yaml_text = """
    mbta:
      api_key: "key"
      route_id: "109"
      poll_interval_seconds: 10
    display:
      width: 128
      height: 64
      brightness: 80
      scroll_speed_fps: 20
    logging:
      level: "INFO"
      log_dir: "logs/"
    """
    path = _write_yaml(tmp_path, yaml_text)

    with pytest.raises(ValueError):
        load_config(path)
