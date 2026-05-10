from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .parser import MessageEvent, SessionAgg


# Calibration window — observations older than this are dropped because
# Anthropic occasionally changes plan limits.
CALIBRATION_DECAY = timedelta(days=30)
# Minimum hits before we trust the empirical estimate enough to render the bar.
MIN_HITS_FOR_BAR = 3


def filter_by_range(
    sessions: Sequence[SessionAgg],
    start: datetime,
    end: datetime,
) -> list[SessionAgg]:
    return [s for s in sessions if start <= s.started_at < end]


def range_from_days(days: float, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = (now or datetime.now(timezone.utc))
    start = end - timedelta(days=days)
    return start, end


def summary(sessions: Sequence[SessionAgg]) -> dict:
    if not sessions:
        return {
            "sessions_tracked": 0,
            "raw_total": 0,
            "weighted_total": 0.0,
            "projects_count": 0,
            "input": 0,
            "output": 0,
            "cache_create": 0,
            "cache_read": 0,
            "msgs_total": 0,
        }
    return {
        "sessions_tracked": len(sessions),
        "raw_total": sum(s.raw_total for s in sessions),
        "weighted_total": sum(s.weighted for s in sessions),
        "projects_count": len({s.project for s in sessions}),
        "input": sum(s.input_tokens for s in sessions),
        "output": sum(s.output_tokens for s in sessions),
        "cache_create": sum(s.cache_create_tokens for s in sessions),
        "cache_read": sum(s.cache_read_tokens for s in sessions),
        "msgs_total": sum(s.message_count for s in sessions),
    }


def by_day(sessions: Sequence[SessionAgg]) -> list[dict]:
    buckets: dict[str, float] = defaultdict(float)
    for s in sessions:
        day = s.started_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        buckets[day] += s.weighted
    rows = []
    for day, w in sorted(buckets.items()):
        # Noon UTC: anchors the bucket so toLocaleDateString resolves to the
        # same calendar day in any reasonable timezone (~ ±11h offset).
        started_iso = f"{day}T12:00:00+00:00"
        rows.append({"date": day, "started_iso": started_iso, "weighted": w})
    return rows


def by_project(sessions: Sequence[SessionAgg]) -> list[dict]:
    total = sum(s.weighted for s in sessions) or 1.0
    buckets: dict[str, dict] = defaultdict(
        lambda: {"weighted": 0.0, "sessions": 0, "msgs": 0}
    )
    for s in sessions:
        b = buckets[s.project]
        b["weighted"] += s.weighted
        b["sessions"] += 1
        b["msgs"] += s.message_count
    rows = [
        {
            "project": project,
            "weighted": b["weighted"],
            "share_pct": b["weighted"] / total * 100,
            "sessions": b["sessions"],
            "msgs": b["msgs"],
        }
        for project, b in buckets.items()
    ]
    rows.sort(key=lambda r: r["weighted"], reverse=True)
    return rows


def by_model(sessions: Sequence[SessionAgg]) -> list[dict]:
    buckets: dict[str, int] = defaultdict(int)
    for s in sessions:
        buckets[s.model] += s.raw_total
    total = sum(buckets.values()) or 1
    rows = [
        {"model": m, "raw": v, "share_pct": v / total * 100}
        for m, v in buckets.items()
    ]
    rows.sort(key=lambda r: r["raw"], reverse=True)
    return rows


def top_sessions(
    sessions: Sequence[SessionAgg], limit: int = 30
) -> tuple[list[dict], int, float]:
    sorted_sessions = sorted(sessions, key=lambda s: s.weighted, reverse=True)
    top = sorted_sessions[:limit]
    others = sorted_sessions[limit:]
    top_rows = [
        {
            "session_id": s.session_id,
            "title": s.title,
            "date": s.started_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "started_iso": s.started_at.astimezone(timezone.utc).isoformat(),
            "project": s.project,
            "msgs": s.message_count,
            "weighted": s.weighted,
        }
        for s in top
    ]
    return top_rows, len(others), sum(s.weighted for s in others)


def build_stats(sessions: Sequence[SessionAgg]) -> dict:
    top, other_count, other_weighted = top_sessions(sessions)
    return {
        "summary": summary(sessions),
        "daily": by_day(sessions),
        "projects": by_project(sessions),
        "models": by_model(sessions),
        "top_sessions": top,
        "other_sessions": {
            "count": other_count,
            "weighted": other_weighted,
        },
    }


def _sum_window(
    events: Sequence[MessageEvent], start: datetime, end: datetime
) -> dict:
    weighted = 0.0
    raw = 0
    sessions: set[str] = set()
    by_model_w: dict[str, float] = defaultdict(float)
    for ev in events:
        if ev.timestamp < start or ev.timestamp >= end:
            continue
        weighted += ev.weighted
        raw += ev.raw_total
        sessions.add(ev.session_id)
        by_model_w[ev.model] += ev.weighted
    duration_h = max((end - start).total_seconds() / 3600.0, 1e-6)
    return {
        "weighted": weighted,
        "raw": raw,
        "sessions": len(sessions),
        "by_model": [
            {"model": m, "weighted": w}
            for m, w in sorted(by_model_w.items(), key=lambda kv: -kv[1])
        ],
        "weighted_per_hour": weighted / duration_h,
    }


def burn_rate(
    events: Sequence[MessageEvent], now: datetime | None = None
) -> dict:
    """Rolling-window burn rate + 24h hourly sparkline.

    Returns weighted-token totals over the last 5h / 24h / 7d windows ending
    at `now`, plus an hourly breakdown of the last 24 hours suitable for a
    sparkline. The weighted figure is a cost proxy, not a fraction of the
    Anthropic subscription quota — the actual quota formula is unpublished.
    """
    n = (now or datetime.now(timezone.utc))
    last_5h = _sum_window(events, n - timedelta(hours=5), n)
    last_24h = _sum_window(events, n - timedelta(hours=24), n)
    last_7d = _sum_window(events, n - timedelta(days=7), n)

    hourly: list[dict] = []
    floor = n.replace(minute=0, second=0, microsecond=0)
    buckets: dict[datetime, float] = defaultdict(float)
    cutoff = floor - timedelta(hours=23)
    for ev in events:
        if ev.timestamp < cutoff or ev.timestamp >= floor + timedelta(hours=1):
            continue
        bucket = ev.timestamp.replace(minute=0, second=0, microsecond=0)
        buckets[bucket] += ev.weighted

    for i in range(24):
        bucket = floor - timedelta(hours=23 - i)
        hourly.append(
            {
                "hour": bucket.isoformat(),
                "weighted": buckets.get(bucket, 0.0),
            }
        )

    return {
        "now": n.isoformat(),
        "last_5h": last_5h,
        "last_24h": last_24h,
        "last_7d": last_7d,
        "hourly_24h": hourly,
    }


def snapshot_at(events: Sequence[MessageEvent], when: datetime) -> dict:
    """Burn-rate snapshot at an arbitrary historical moment.

    Returns the same numbers `burn_rate` would compute, but pretending `when`
    is "now". Used to capture the burn state at the exact moment a rate-limit
    hit landed — that's the empirical signal we calibrate against.
    """
    last_5h = _sum_window(events, when - timedelta(hours=5), when)
    last_24h = _sum_window(events, when - timedelta(hours=24), when)
    last_7d = _sum_window(events, when - timedelta(days=7), when)
    return {
        "weighted_5h": last_5h["weighted"],
        "weighted_24h": last_24h["weighted"],
        "weighted_7d": last_7d["weighted"],
        "model_mix": {
            row["model"]: row["weighted"] for row in last_5h["by_model"]
        },
    }


def calibrate_quota(
    hit_rows: Sequence[dict],
    now: datetime | None = None,
) -> dict:
    """Estimate the empirical 5h / weekly quota from past limit hits.

    `hit_rows` is what `storage.load_recent` returns. Each row carries the
    burn-rate snapshot at the moment the user got blocked. The median of
    those snapshots is our best guess at the personal cap.

    Returns:
        {
            "n": int,                     # observations within window
            "ready": bool,                # n >= MIN_HITS_FOR_BAR
            "p5h": float | None,          # median weighted_5h at hit
            "p_weekly": float | None,     # median weighted_7d at hit
            "spread_pct_5h": float | None # interquartile / median, %
        }
    """
    n_now = now or datetime.now(timezone.utc)
    cutoff = n_now - CALIBRATION_DECAY

    recent: list[dict] = []
    for r in hit_rows:
        ts_iso = r.get("ts_iso")
        if not ts_iso:
            continue
        try:
            ts = datetime.fromisoformat(ts_iso)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            recent.append(r)

    n = len(recent)
    if n == 0:
        return {
            "n": 0, "ready": False,
            "p5h": None, "p_weekly": None, "spread_pct_5h": None,
        }

    vals_5h = [r["weighted_5h"] for r in recent if r.get("weighted_5h")]
    vals_7d = [r["weighted_7d"] for r in recent if r.get("weighted_7d")]

    p5h = statistics.median(vals_5h) if vals_5h else None
    p_weekly = statistics.median(vals_7d) if vals_7d else None

    spread_pct_5h = None
    if len(vals_5h) >= 4 and p5h:
        q = statistics.quantiles(vals_5h, n=4)
        iqr = q[2] - q[0]
        spread_pct_5h = (iqr / p5h) * 100

    return {
        "n": n,
        "ready": n >= MIN_HITS_FOR_BAR,
        "p5h": p5h,
        "p_weekly": p_weekly,
        "spread_pct_5h": spread_pct_5h,
    }
