from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_code_token_meter.aggregator import (
    build_stats,
    burn_rate,
    by_day,
    by_project,
    filter_by_range,
    summary,
    top_sessions,
)
from claude_code_token_meter.parser import (
    MessageEvent,
    SessionAgg,
    _project_label,
    aggregate_sessions,
    parse_all,
    parse_all_events,
)


def _write_session(path: Path, session_id: str, cwd: str, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for ts, model, usage in entries:
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": ts,
                        "sessionId": session_id,
                        "cwd": cwd,
                        "message": {"model": model, "usage": usage},
                    }
                )
                + "\n"
            )


def test_project_label():
    assert _project_label("/Users/x/Cursor/CoinKeeper") == "Cursor/CoinKeeper"
    assert _project_label("/single") == "single"
    assert _project_label("") == "(unknown)"


def test_parse_all_aggregates_per_session(tmp_path: Path):
    proj_dir = tmp_path / "projects"
    _write_session(
        proj_dir / "p1" / "abc.jsonl",
        "abc-session",
        "/Users/x/Cursor/Foo",
        [
            (
                "2026-05-01T10:00:00Z",
                "claude-opus-4-7",
                {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 1000,
                },
            ),
            (
                "2026-05-01T10:05:00Z",
                "claude-opus-4-7",
                {
                    "input_tokens": 5,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 50,
                    "cache_read_input_tokens": 500,
                },
            ),
        ],
    )
    _write_session(
        proj_dir / "p2" / "def.jsonl",
        "def-session",
        "/Users/x/Cursor/Bar",
        [
            (
                "2026-05-02T10:00:00Z",
                "claude-sonnet-4-6",
                {"input_tokens": 1, "output_tokens": 2},
            ),
        ],
    )

    sessions = parse_all(proj_dir)
    sessions.sort(key=lambda s: s.session_id)

    assert len(sessions) == 2
    s1 = next(s for s in sessions if s.session_id == "abc-session")
    assert s1.project == "Cursor/Foo"
    assert s1.input_tokens == 15
    assert s1.output_tokens == 30
    assert s1.cache_create_tokens == 150
    assert s1.cache_read_tokens == 1500
    assert s1.message_count == 2
    assert s1.raw_total == 15 + 30 + 150 + 1500
    expected_w = 15 * 1 + 30 * 5 + 150 * 1.25 + 1500 * 0.1
    assert s1.weighted == expected_w


def test_skips_non_assistant_and_no_usage(tmp_path: Path):
    p = tmp_path / "x.jsonl"
    p.write_text(
        json.dumps({"type": "user", "timestamp": "2026-05-01T10:00:00Z"}) + "\n"
        + json.dumps({"type": "assistant", "timestamp": "2026-05-01T10:01:00Z",
                      "sessionId": "s1", "message": {"model": "x"}}) + "\n"
        + "not json\n"
        + json.dumps({"type": "assistant", "timestamp": "2026-05-01T10:02:00Z",
                      "sessionId": "s1", "cwd": "/a/b",
                      "message": {"model": "m", "usage": {"input_tokens": 1, "output_tokens": 2}}}) + "\n"
    )
    sessions = parse_all(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].input_tokens == 1
    assert sessions[0].output_tokens == 2


def _mk(session_id: str, project: str, when: datetime, weighted_seed: int) -> SessionAgg:
    s = SessionAgg(
        session_id=session_id,
        project=project,
        cwd="/x/" + project,
        started_at=when,
        model="claude-opus-4-7",
        input_tokens=weighted_seed,
        output_tokens=weighted_seed,
        cache_create_tokens=weighted_seed,
        cache_read_tokens=weighted_seed,
        message_count=1,
    )
    return s


def test_aggregations():
    now = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)
    sessions = [
        _mk("a", "Cursor/A", now.replace(day=1), 100),
        _mk("b", "Cursor/A", now.replace(day=2), 50),
        _mk("c", "Cursor/B", now.replace(day=2), 200),
    ]
    summ = summary(sessions)
    assert summ["sessions_tracked"] == 3
    assert summ["projects_count"] == 2

    daily = by_day(sessions)
    assert [d["date"] for d in daily] == ["2026-05-01", "2026-05-02"]
    # Phase 2.5: every daily row carries a parseable ISO timestamp so the
    # frontend can render it in the user's local timezone.
    for d in daily:
        assert "started_iso" in d
        parsed = datetime.fromisoformat(d["started_iso"])
        assert parsed.tzinfo is not None
        assert parsed.strftime("%Y-%m-%d") == d["date"]

    projects = by_project(sessions)
    assert projects[0]["project"] == "Cursor/B"
    assert sum(p["share_pct"] for p in projects) == 100.0

    in_range = filter_by_range(
        sessions,
        datetime(2026, 5, 2, tzinfo=timezone.utc),
        datetime(2026, 5, 3, tzinfo=timezone.utc),
    )
    assert len(in_range) == 2

    top, other_count, other_weighted = top_sessions(sessions, limit=2)
    assert len(top) == 2
    assert other_count == 1
    assert other_weighted > 0
    # Phase 2.5: each top-session row carries a parseable ISO timestamp.
    for row in top:
        assert "started_iso" in row
        parsed = datetime.fromisoformat(row["started_iso"])
        assert parsed.tzinfo is not None


def test_build_stats_shape():
    s = _mk("a", "Cursor/A", datetime(2026, 5, 1, tzinfo=timezone.utc), 10)
    stats = build_stats([s])
    for key in ("summary", "daily", "projects", "models", "top_sessions", "other_sessions"):
        assert key in stats
    assert stats["other_sessions"]["count"] == 0


def test_parse_all_events_yields_one_event_per_assistant_msg(tmp_path: Path):
    proj = tmp_path / "projects" / "p"
    _write_session(
        proj / "a.jsonl",
        "s1",
        "/x/a",
        [
            ("2026-05-01T10:00:00Z", "claude-opus-4-7", {"input_tokens": 1, "output_tokens": 2}),
            ("2026-05-01T10:01:00Z", "claude-opus-4-7", {"input_tokens": 3, "output_tokens": 4}),
        ],
    )
    events = parse_all_events(tmp_path / "projects")
    assert len(events) == 2
    assert events[0].timestamp < events[1].timestamp
    sessions = aggregate_sessions(events)
    assert len(sessions) == 1
    assert sessions[0].input_tokens == 4
    assert sessions[0].output_tokens == 6
    assert sessions[0].message_count == 2


def _ev(when: datetime, weighted_seed: int, sid: str = "s") -> MessageEvent:
    return MessageEvent(
        timestamp=when,
        session_id=sid,
        project="Cursor/A",
        cwd="/x/A",
        model="claude-opus-4-7",
        input_tokens=weighted_seed,
        output_tokens=weighted_seed,
        cache_create_tokens=0,
        cache_read_tokens=0,
    )


def test_burn_rate_windows():
    now = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)
    events = [
        _ev(now - timedelta(hours=2), 10),       # in 5h, 24h, 7d
        _ev(now - timedelta(hours=10), 10, "b"), # in 24h, 7d
        _ev(now - timedelta(days=3), 10, "c"),   # in 7d only
        _ev(now - timedelta(days=10), 10, "d"),  # outside all
    ]
    br = burn_rate(events, now=now)
    # weighted = input*1 + output*5 = 10 + 50 = 60 per event
    assert br["last_5h"]["weighted"] == 60
    assert br["last_24h"]["weighted"] == 120
    assert br["last_7d"]["weighted"] == 180
    assert len(br["hourly_24h"]) == 24
    # the most recent bucket should be the hour containing `now`
    assert br["hourly_24h"][-1]["hour"].startswith("2026-05-09T12:00")


def test_burn_rate_empty():
    now = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)
    br = burn_rate([], now=now)
    assert br["last_5h"]["weighted"] == 0
    assert br["last_5h"]["sessions"] == 0
    assert len(br["hourly_24h"]) == 24
