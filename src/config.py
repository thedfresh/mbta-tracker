"""Configuration loader for the MBTA Transit Display app."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from dotenv import load_dotenv
import yaml


@dataclass(frozen=True)
class MBTAConfig:
    """MBTA API configuration."""

    api_key: str
    route_id: str
    stop_id: str
    terminal_stop_id: str
    poll_interval_seconds: int


@dataclass(frozen=True)
class DisplayConfig:
    """Display configuration for rendering and hardware."""

    width: int
    height: int
    brightness: int
    scroll_speed_fps: int


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str
    log_dir: str


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    mbta: MBTAConfig
    display: DisplayConfig
    log: LoggingConfig


def _require_key(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise ValueError(f"Missing required key '{key}' in {context} config")
    return mapping[key]


def load_config(path: str = "config/config.yaml") -> AppConfig:
    """Load application configuration from a YAML file."""
    load_dotenv()
    api_key = os.environ.get("MBTA_API_KEY", "")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"Config file not found: {path}") from exc

    if not isinstance(data, dict):
        raise ValueError("Config file must contain a mapping at the top level")

    mbta_section = _require_key(data, "mbta", "mbta")
    display_section = _require_key(data, "display", "display")
    logging_section = _require_key(data, "logging", "logging")

    if not isinstance(mbta_section, dict):
        raise ValueError("'mbta' config must be a mapping")
    if not isinstance(display_section, dict):
        raise ValueError("'display' config must be a mapping")
    if not isinstance(logging_section, dict):
        raise ValueError("'logging' config must be a mapping")

    mbta = MBTAConfig(
        api_key=api_key,
        route_id=_require_key(mbta_section, "route_id", "mbta"),
        stop_id=_require_key(mbta_section, "stop_id", "mbta"),
        terminal_stop_id=_require_key(mbta_section, "terminal_stop_id", "mbta"),
        poll_interval_seconds=_require_key(mbta_section, "poll_interval_seconds", "mbta"),
    )

    display = DisplayConfig(
        width=_require_key(display_section, "width", "display"),
        height=_require_key(display_section, "height", "display"),
        brightness=_require_key(display_section, "brightness", "display"),
        scroll_speed_fps=_require_key(display_section, "scroll_speed_fps", "display"),
    )

    logging = LoggingConfig(
        level=_require_key(logging_section, "level", "logging"),
        log_dir=_require_key(logging_section, "log_dir", "logging"),
    )

    return AppConfig(mbta=mbta, display=display, log=logging)
