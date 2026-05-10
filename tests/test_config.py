"""Tests for the manual quota config module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_code_token_meter import config


def test_load_returns_empty_when_file_missing(tmp_path: Path) -> None:
    cfg = config.load(tmp_path / "nope.json")
    assert cfg.quota_5h is None
    assert cfg.quota_weekly is None


def test_load_handles_malformed_json(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text("{ this is not json")
    cfg = config.load(p)
    assert cfg.quota_5h is None
    assert cfg.quota_weekly is None


def test_load_handles_non_object_root(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text("[1, 2, 3]")
    cfg = config.load(p)
    assert cfg.quota_5h is None
    assert cfg.quota_weekly is None


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dir" / "config.json"
    config.save(config.QuotaConfig(quota_5h=6_000_000), p)
    assert p.exists()
    data = json.loads(p.read_text())
    assert data == {"quota_5h": 6_000_000, "quota_weekly": None}


def test_save_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    cfg_in = config.QuotaConfig(quota_5h=5_000_000, quota_weekly=180_000_000)
    config.save(cfg_in, p)
    cfg_out = config.load(p)
    assert cfg_out == cfg_in


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, None),
        ("", None),
        ("0", None),
        ("-5", None),
        ("abc", None),
        (0, None),
        (-1, None),
        ("123", 123),
        (123, 123),
        (12.7, 12),
    ],
)
def test_coerce_positive_int(raw, expected) -> None:
    assert config._coerce_positive_int(raw) == expected


def test_load_coerces_string_values(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"quota_5h": "6000000", "quota_weekly": "0"}))
    cfg = config.load(p)
    assert cfg.quota_5h == 6_000_000
    assert cfg.quota_weekly is None  # 0 is rejected


def test_merge_overrides_query_param_wins(tmp_path: Path) -> None:
    base = config.QuotaConfig(quota_5h=5_000_000, quota_weekly=100_000_000)
    merged = config.merge_overrides(base, quota_5h="9000000")
    assert merged.quota_5h == 9_000_000
    assert merged.quota_weekly == 100_000_000  # untouched


def test_merge_overrides_blank_keeps_base() -> None:
    base = config.QuotaConfig(quota_5h=5_000_000)
    merged = config.merge_overrides(base, quota_5h="", quota_weekly=None)
    assert merged.quota_5h == 5_000_000
    assert merged.quota_weekly is None


def test_merge_overrides_invalid_string_keeps_base() -> None:
    base = config.QuotaConfig(quota_5h=5_000_000)
    merged = config.merge_overrides(base, quota_5h="not-a-number")
    assert merged.quota_5h == 5_000_000


def test_default_config_path_under_xdg_config_home() -> None:
    # The path must be under the user's home dir; we don't enforce XDG layout
    # but the layout we ship with must be stable for users to find it.
    p = config.default_config_path()
    assert p.name == "config.json"
    assert p.parent.name == "claude-code-token-meter"
    assert p.parent.parent.name == ".config"
