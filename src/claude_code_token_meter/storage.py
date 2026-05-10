"""SQLite storage for clustered rate-limit events.

The schema is intentionally tiny — we only need rows we can ship through
calibration (`weighted_5h_at_hit` etc.). Storage is idempotent on
`(ts_iso, reset_text)` so re-scanning the JSONL never duplicates events.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .detector import LimitEvent


SCHEMA = """
CREATE TABLE IF NOT EXISTS limit_hits (
    ts_iso        TEXT NOT NULL,
    reset_text    TEXT NOT NULL,
    session_id    TEXT,
    cwd           TEXT,
    cluster_count INTEGER NOT NULL DEFAULT 1,
    weighted_5h   REAL,
    weighted_24h  REAL,
    weighted_7d   REAL,
    model_mix     TEXT,        -- JSON: {"opus": 0.7, "sonnet": 0.3}
    PRIMARY KEY (ts_iso, reset_text)
);
"""


def default_db_path() -> Path:
    """Live next to the JSONL logs so a single backup catches everything."""
    return Path.home() / ".claude" / "token-meter.db"


@contextmanager
def _connect(db_path: Path) -> Iterable[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_events(
    db_path: Path,
    events: Iterable[LimitEvent],
    snapshots: dict[str, dict] | None = None,
) -> int:
    """Insert or update clustered limit events.

    `snapshots` is `{event_key: {weighted_5h, weighted_24h, weighted_7d, model_mix}}`
    where `event_key = f"{ts_iso}|{reset_text}"`. Snapshots are computed from
    burn-rate history at event time — see `aggregator.snapshot_at`.

    Returns the number of new rows inserted (excludes updates of existing).
    """
    snapshots = snapshots or {}
    inserted = 0
    with _connect(db_path) as conn:
        for ev in events:
            ts_iso = ev.started_at.astimezone(timezone.utc).isoformat()
            key = f"{ts_iso}|{ev.reset_text}"
            snap = snapshots.get(key, {})
            mix_json = (
                json.dumps(snap["model_mix"]) if snap.get("model_mix") else None
            )
            params = (
                ts_iso,
                ev.reset_text,
                ev.session_id or None,
                ev.cwd or None,
                ev.count,
                snap.get("weighted_5h"),
                snap.get("weighted_24h"),
                snap.get("weighted_7d"),
                mix_json,
            )
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO limit_hits (
                    ts_iso, reset_text, session_id, cwd, cluster_count,
                    weighted_5h, weighted_24h, weighted_7d, model_mix
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                # Row exists — refresh mutable fields (cluster_count grows as
                # we re-scan the JSONL; snapshot stays sticky if already set).
                conn.execute(
                    """
                    UPDATE limit_hits SET
                        cluster_count = ?,
                        weighted_5h   = COALESCE(weighted_5h, ?),
                        weighted_24h  = COALESCE(weighted_24h, ?),
                        weighted_7d   = COALESCE(weighted_7d, ?),
                        model_mix     = COALESCE(model_mix, ?)
                    WHERE ts_iso = ? AND reset_text = ?
                    """,
                    (
                        ev.count,
                        snap.get("weighted_5h"),
                        snap.get("weighted_24h"),
                        snap.get("weighted_7d"),
                        mix_json,
                        ts_iso,
                        ev.reset_text,
                    ),
                )
    return inserted


def load_recent(db_path: Path, since: datetime | None = None) -> list[dict]:
    """Return stored limit-hit rows newer than `since` (inclusive)."""
    if not db_path.exists():
        return []
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if since is not None:
            rows = conn.execute(
                "SELECT * FROM limit_hits WHERE ts_iso >= ? ORDER BY ts_iso ASC",
                (since.astimezone(timezone.utc).isoformat(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM limit_hits ORDER BY ts_iso ASC"
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("model_mix"):
            try:
                d["model_mix"] = json.loads(d["model_mix"])
            except (json.JSONDecodeError, TypeError):
                d["model_mix"] = None
        out.append(d)
    return out
