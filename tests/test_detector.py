from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_code_token_meter.aggregator import (
    MIN_HITS_FOR_BAR,
    calibrate_quota,
    snapshot_at,
)
from claude_code_token_meter.detector import (
    LimitEvent,
    cluster_hits,
    hit_from_record,
    is_rate_limit_record,
)
from claude_code_token_meter.parser import (
    MessageEvent,
    parse_all_events_and_hits,
)
from claude_code_token_meter.storage import load_recent, upsert_events


# ---------- detector.is_rate_limit_record / hit_from_record ----------

_LIMIT_RECORD = {
    "type": "assistant",
    "timestamp": "2026-02-19T13:56:28.965Z",
    "sessionId": "46a0be04-1ad8-4635-8431-8fdff3d657ee",
    "cwd": "/Users/x/Cursor/HeyMetrics",
    "isSidechain": True,
    "isApiErrorMessage": True,
    "error": "rate_limit",
    "message": {
        "model": "<synthetic>",
        "role": "assistant",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "content": [
            {"type": "text", "text": "You've hit your limit · resets 5pm (Europe/Madrid)"}
        ],
    },
}


def test_is_rate_limit_record_positive():
    assert is_rate_limit_record(_LIMIT_RECORD) is True


def test_is_rate_limit_record_other_errors_rejected():
    assert is_rate_limit_record({"isApiErrorMessage": True, "error": "server_error"}) is False
    assert is_rate_limit_record({"isApiErrorMessage": True, "error": "max_output_tokens"}) is False
    assert is_rate_limit_record({"isApiErrorMessage": False, "error": "rate_limit"}) is False
    assert is_rate_limit_record({}) is False


def test_hit_from_record_extracts_fields():
    hit = hit_from_record(_LIMIT_RECORD)
    assert hit is not None
    assert hit.timestamp == datetime(2026, 2, 19, 13, 56, 28, 965000, tzinfo=timezone.utc)
    assert hit.session_id == "46a0be04-1ad8-4635-8431-8fdff3d657ee"
    assert hit.cwd == "/Users/x/Cursor/HeyMetrics"
    assert "resets 5pm" in hit.reset_text
    assert hit.is_sidechain is True


def test_hit_from_record_string_content():
    rec = {**_LIMIT_RECORD, "message": {"content": "raw string limit msg"}}
    hit = hit_from_record(rec)
    assert hit is not None
    assert hit.reset_text == "raw string limit msg"


def test_hit_from_record_returns_none_on_bad_input():
    assert hit_from_record({"isApiErrorMessage": False, "error": "rate_limit"}) is None
    bad_ts = {**_LIMIT_RECORD, "timestamp": "not-a-date"}
    assert hit_from_record(bad_ts) is None


# ---------- detector.cluster_hits ----------

def _hit(when: datetime, text: str = "resets 3am", sid: str = "s") -> dict:
    return {
        **_LIMIT_RECORD,
        "timestamp": when.isoformat().replace("+00:00", "Z"),
        "sessionId": sid,
        "message": {**_LIMIT_RECORD["message"], "content": [{"type": "text", "text": text}]},
    }


def test_cluster_collapses_close_same_text_hits():
    base = datetime(2026, 2, 19, 21, 48, 0, tzinfo=timezone.utc)
    raw = [
        hit_from_record(_hit(base + timedelta(seconds=0))),
        hit_from_record(_hit(base + timedelta(seconds=2))),
        hit_from_record(_hit(base + timedelta(seconds=30))),
        hit_from_record(_hit(base + timedelta(minutes=3))),
        hit_from_record(_hit(base + timedelta(minutes=27))),  # still inside 30m
    ]
    events = cluster_hits(raw)
    assert len(events) == 1
    assert events[0].count == 5
    assert events[0].started_at == base


def test_cluster_separates_distant_hits():
    base = datetime(2026, 2, 19, 13, 56, 0, tzinfo=timezone.utc)
    raw = [
        hit_from_record(_hit(base, text="resets 5pm")),
        hit_from_record(_hit(base + timedelta(hours=8), text="resets 3am")),
    ]
    events = cluster_hits(raw)
    assert len(events) == 2
    assert {e.reset_text for e in events} == {"resets 5pm", "resets 3am"}


def test_cluster_separates_different_reset_text_even_when_close():
    base = datetime(2026, 2, 19, 13, 56, 0, tzinfo=timezone.utc)
    raw = [
        hit_from_record(_hit(base, text="resets 5pm")),
        hit_from_record(_hit(base + timedelta(seconds=10), text="resets 6pm")),
    ]
    events = cluster_hits(raw)
    assert len(events) == 2


# ---------- parser.parse_all_events_and_hits ----------

def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")


def test_parser_returns_both_events_and_hits(tmp_path: Path):
    proj = tmp_path / "projects" / "p"
    real_msg = {
        "type": "assistant",
        "timestamp": "2026-05-01T10:00:00Z",
        "sessionId": "s1",
        "cwd": "/x/A",
        "message": {
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 100, "output_tokens": 200},
        },
    }
    limit_msg = {**_LIMIT_RECORD, "timestamp": "2026-05-01T10:05:00Z", "sessionId": "s1"}
    _write_jsonl(proj / "session.jsonl", [real_msg, limit_msg])

    events, hits = parse_all_events_and_hits(tmp_path / "projects")
    assert len(events) == 1
    assert events[0].input_tokens == 100
    assert events[0].output_tokens == 200
    assert len(hits) == 1
    assert hits[0].session_id == "s1"


# ---------- aggregator.snapshot_at ----------

def _ev(when: datetime, w_seed: int, sid: str = "s") -> MessageEvent:
    return MessageEvent(
        timestamp=when, session_id=sid, project="p", cwd="/x/p",
        model="claude-opus-4-7",
        input_tokens=w_seed, output_tokens=w_seed,
        cache_create_tokens=0, cache_read_tokens=0,
    )


def test_snapshot_at_pretends_when_is_now():
    when = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)
    events = [
        _ev(when - timedelta(hours=1), 10),  # weighted = 60, in 5h+24h+7d
        _ev(when - timedelta(hours=10), 10), # in 24h+7d
        _ev(when - timedelta(days=3), 10),   # in 7d
    ]
    snap = snapshot_at(events, when)
    assert snap["weighted_5h"] == 60
    assert snap["weighted_24h"] == 120
    assert snap["weighted_7d"] == 180
    assert "claude-opus-4-7" in snap["model_mix"]


# ---------- aggregator.calibrate_quota ----------

def test_calibration_below_threshold_not_ready():
    rows = [
        {"ts_iso": "2026-05-01T10:00:00+00:00", "weighted_5h": 100.0, "weighted_7d": 700.0},
        {"ts_iso": "2026-05-02T10:00:00+00:00", "weighted_5h": 110.0, "weighted_7d": 720.0},
    ]
    cal = calibrate_quota(rows, now=datetime(2026, 5, 9, tzinfo=timezone.utc))
    assert cal["n"] == 2
    assert cal["ready"] is False


def test_calibration_returns_median_when_ready():
    rows = [
        {"ts_iso": f"2026-05-0{i}T10:00:00+00:00", "weighted_5h": v, "weighted_7d": v * 7}
        for i, v in enumerate([100.0, 200.0, 300.0, 400.0, 500.0], start=1)
    ]
    cal = calibrate_quota(rows, now=datetime(2026, 5, 9, tzinfo=timezone.utc))
    assert cal["n"] == 5
    assert cal["ready"] is True
    assert cal["p5h"] == 300.0
    assert cal["p_weekly"] == 300.0 * 7
    # exclusive-method quartiles on [100,200,300,400,500] → Q1=150, Q3=450,
    # IQR=300, median=300 → spread = 100%
    assert cal["spread_pct_5h"] is not None
    assert 95 < cal["spread_pct_5h"] < 105


def test_calibration_drops_observations_older_than_30d():
    now = datetime(2026, 5, 9, tzinfo=timezone.utc)
    rows = [
        # 4 fresh
        *[{"ts_iso": (now - timedelta(days=i)).isoformat(), "weighted_5h": 100.0, "weighted_7d": 700.0}
          for i in range(1, 5)],
        # 1 ancient
        {"ts_iso": (now - timedelta(days=60)).isoformat(), "weighted_5h": 99999.0, "weighted_7d": 1.0},
    ]
    cal = calibrate_quota(rows, now=now)
    assert cal["n"] == 4
    assert cal["p5h"] == 100.0   # ancient outlier ignored


def test_calibration_min_hits_threshold():
    assert MIN_HITS_FOR_BAR == 3


# ---------- storage round-trip ----------

def test_storage_upsert_and_load(tmp_path: Path):
    db = tmp_path / "tm.db"
    when = datetime(2026, 2, 19, 21, 48, 0, tzinfo=timezone.utc)
    ev = LimitEvent(
        started_at=when,
        session_id="abc",
        cwd="/x/a",
        reset_text="resets 3am",
        count=4,
    )
    snapshots = {
        f"{when.isoformat()}|resets 3am": {
            "weighted_5h": 1234.0,
            "weighted_24h": 5000.0,
            "weighted_7d": 9999.0,
            "model_mix": {"claude-opus-4-7": 1234.0},
        }
    }

    inserted_first = upsert_events(db, [ev], snapshots)
    assert inserted_first == 1

    inserted_second = upsert_events(db, [ev], snapshots)
    assert inserted_second == 0  # idempotent

    rows = load_recent(db)
    assert len(rows) == 1
    assert rows[0]["weighted_5h"] == 1234.0
    assert rows[0]["cluster_count"] == 4
    assert rows[0]["model_mix"] == {"claude-opus-4-7": 1234.0}


def test_storage_load_recent_filters_by_since(tmp_path: Path):
    db = tmp_path / "tm.db"
    old = LimitEvent(
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        session_id="o", cwd="/x/o", reset_text="old", count=1,
    )
    new = LimitEvent(
        started_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        session_id="n", cwd="/x/n", reset_text="new", count=1,
    )
    upsert_events(db, [old, new])
    recent = load_recent(db, since=datetime(2026, 4, 1, tzinfo=timezone.utc))
    assert len(recent) == 1
    assert recent[0]["reset_text"] == "new"
