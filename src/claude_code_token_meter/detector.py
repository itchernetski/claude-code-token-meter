"""Detect rate-limit hits in raw Claude Code JSONL records.

A rate-limit hit is a synthetic assistant record CC writes to the session
log when Anthropic refuses a request because the user's plan window is
exhausted. See `workspace/limit-signature.md` for the field shape.

This module does not parse files — it operates on already-decoded JSON
records emitted from the same single-pass scan as `parser._parse_file_events`,
so detection is free.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Iterable


# How close two raw hits must be to be considered the same blocked event.
# Empirically, retries from one block cluster within ~5 minutes; we widen
# to 30m to absorb manual retries and subagent propagation.
CLUSTER_WINDOW = timedelta(minutes=30)


@dataclass(slots=True)
class LimitHit:
    """A single raw rate_limit JSONL record."""
    timestamp: datetime
    session_id: str
    cwd: str
    reset_text: str           # e.g. "resets 5pm (Europe/Madrid)" or full content
    is_sidechain: bool


@dataclass(slots=True)
class LimitEvent:
    """A clustered rate-limit event: the moment the cap was actually hit.

    `started_at` is the earliest hit in the cluster; `count` is how many raw
    records collapsed into it.
    """
    started_at: datetime
    session_id: str
    cwd: str
    reset_text: str
    count: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        return d


def is_rate_limit_record(entry: dict) -> bool:
    """Return True iff `entry` is a synthetic rate-limit record.

    Criteria are documented in workspace/limit-signature.md:
    `error == "rate_limit"` AND `isApiErrorMessage == true`.
    """
    return (
        entry.get("error") == "rate_limit"
        and entry.get("isApiErrorMessage") is True
    )


def hit_from_record(entry: dict) -> LimitHit | None:
    """Build a `LimitHit` from a raw JSONL entry, or None if not a hit."""
    if not is_rate_limit_record(entry):
        return None
    ts_raw = entry.get("timestamp")
    if not isinstance(ts_raw, str):
        return None
    try:
        if ts_raw.endswith("Z"):
            ts_raw = ts_raw[:-1] + "+00:00"
        ts = datetime.fromisoformat(ts_raw).astimezone(timezone.utc)
    except ValueError:
        return None

    sid = entry.get("sessionId") or ""
    cwd = entry.get("cwd") or ""

    reset_text = ""
    msg = entry.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    txt = c.get("text")
                    if isinstance(txt, str):
                        reset_text = txt
                        break
        elif isinstance(content, str):
            reset_text = content

    return LimitHit(
        timestamp=ts,
        session_id=sid,
        cwd=cwd,
        reset_text=reset_text,
        is_sidechain=bool(entry.get("isSidechain")),
    )


def cluster_hits(hits: Iterable[LimitHit]) -> list[LimitEvent]:
    """Collapse hits with the same reset text + close in time into one event.

    Two hits belong to the same event iff:
      - they share the same `reset_text` (different windows would say
        different reset times), AND
      - they are within `CLUSTER_WINDOW` of each other.

    The earliest hit's timestamp / session / cwd is canonical for the event.
    """
    sorted_hits = sorted(hits, key=lambda h: h.timestamp)
    events: list[LimitEvent] = []
    for h in sorted_hits:
        attached = False
        for ev in events:
            if (
                ev.reset_text == h.reset_text
                and (h.timestamp - ev.started_at) <= CLUSTER_WINDOW
            ):
                ev.count += 1
                attached = True
                break
        if not attached:
            events.append(
                LimitEvent(
                    started_at=h.timestamp,
                    session_id=h.session_id,
                    cwd=h.cwd,
                    reset_text=h.reset_text,
                    count=1,
                )
            )
    return events
