"""User-overridable quota config persisted on disk.

Anthropic does not publish the formula for plan quotas, so we offer a manual
override: the user types in their own estimate of `quota_5h` and
`quota_weekly` (weighted tokens) and the dashboard renders progress bars
against those numbers. Both fields are independent and optional.

File: ``~/.config/claude-code-token-meter/config.json``

Schema::

    {
        "quota_5h": int | null,
        "quota_weekly": int | null
    }

A missing or null field means "no manual override" — the UI falls back to
the empirical calibration bar (see aggregator.calibrate_quota) or hides the
bar entirely.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class QuotaConfig:
    quota_5h: int | None = None
    quota_weekly: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def default_config_path() -> Path:
    return Path.home() / ".config" / "claude-code-token-meter" / "config.json"


def load(path: Path | None = None) -> QuotaConfig:
    p = path or default_config_path()
    if not p.exists():
        return QuotaConfig()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return QuotaConfig()
    if not isinstance(data, dict):
        return QuotaConfig()
    return QuotaConfig(
        quota_5h=_coerce_positive_int(data.get("quota_5h")),
        quota_weekly=_coerce_positive_int(data.get("quota_weekly")),
    )


def save(cfg: QuotaConfig, path: Path | None = None) -> None:
    p = path or default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg.to_dict(), indent=2) + "\n", encoding="utf-8")


def merge_overrides(
    base: QuotaConfig,
    quota_5h: int | str | None = None,
    quota_weekly: int | str | None = None,
) -> QuotaConfig:
    """Apply per-request query-param overrides on top of the persisted config.

    Used so power users can pin a quota for a single request via
    ``?quota_5h=...&quota_weekly=...`` without rewriting the saved file.
    """
    return QuotaConfig(
        quota_5h=_coerce_positive_int(quota_5h) or base.quota_5h,
        quota_weekly=_coerce_positive_int(quota_weekly) or base.quota_weekly,
    )


def _coerce_positive_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None
