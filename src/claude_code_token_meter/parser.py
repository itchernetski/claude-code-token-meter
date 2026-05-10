from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from .detector import LimitHit, hit_from_record

WEIGHT_INPUT = 1.0
WEIGHT_OUTPUT = 5.0
WEIGHT_CACHE_CREATE = 1.25
WEIGHT_CACHE_READ = 0.1


def weighted_of(input_t: int, output_t: int, cache_create: int, cache_read: int) -> float:
    return (
        input_t * WEIGHT_INPUT
        + output_t * WEIGHT_OUTPUT
        + cache_create * WEIGHT_CACHE_CREATE
        + cache_read * WEIGHT_CACHE_READ
    )


@dataclass(slots=True)
class MessageEvent:
    timestamp: datetime
    session_id: str
    project: str
    cwd: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_create_tokens: int
    cache_read_tokens: int

    @property
    def raw_total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_create_tokens
            + self.cache_read_tokens
        )

    @property
    def weighted(self) -> float:
        return weighted_of(
            self.input_tokens,
            self.output_tokens,
            self.cache_create_tokens,
            self.cache_read_tokens,
        )


@dataclass
class SessionAgg:
    session_id: str
    project: str
    cwd: str
    started_at: datetime
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_create_tokens: int = 0
    cache_read_tokens: int = 0
    message_count: int = 0
    models_used: set[str] = field(default_factory=set)

    @property
    def raw_total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_create_tokens
            + self.cache_read_tokens
        )

    @property
    def weighted(self) -> float:
        return weighted_of(
            self.input_tokens,
            self.output_tokens,
            self.cache_create_tokens,
            self.cache_read_tokens,
        )

    @property
    def title(self) -> str:
        return self.session_id[:8]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        d["models_used"] = sorted(self.models_used)
        d["raw_total"] = self.raw_total
        d["weighted"] = self.weighted
        d["title"] = self.title
        return d


def _project_label(cwd: str) -> str:
    if not cwd:
        return "(unknown)"
    parts = [p for p in cwd.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else "(unknown)"


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_file(path: Path) -> tuple[list[MessageEvent], list[LimitHit]]:
    """Single-pass parse: extract MessageEvents AND raw rate-limit hits."""
    events: list[MessageEvent] = []
    hits: list[LimitHit] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Rate-limit detection runs on every record — synthetic
                # error records also have type=="assistant" but their usage
                # is all zeros, so they'd be ignored as MessageEvents.
                hit = hit_from_record(entry)
                if hit is not None:
                    hits.append(hit)
                    continue  # synthetic records carry no real usage

                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue

                session_id = entry.get("sessionId")
                if not session_id:
                    continue

                ts = _parse_timestamp(entry.get("timestamp"))
                if ts is None:
                    continue

                cwd = entry.get("cwd") or ""
                events.append(
                    MessageEvent(
                        timestamp=ts,
                        session_id=session_id,
                        project=_project_label(cwd),
                        cwd=cwd,
                        model=msg.get("model") or "unknown",
                        input_tokens=int(usage.get("input_tokens") or 0),
                        output_tokens=int(usage.get("output_tokens") or 0),
                        cache_create_tokens=int(
                            usage.get("cache_creation_input_tokens") or 0
                        ),
                        cache_read_tokens=int(
                            usage.get("cache_read_input_tokens") or 0
                        ),
                    )
                )
    except (OSError, UnicodeDecodeError):
        pass
    return events, hits


def _parse_file_events(path: Path) -> list[MessageEvent]:
    """Backwards-compatible accessor — drops limit hits."""
    events, _ = _parse_file(path)
    return events


def parse_all_events(projects_dir: Path) -> list[MessageEvent]:
    """Return every assistant message event with usage from JSONL logs."""
    events, _ = parse_all_events_and_hits(projects_dir)
    return events


def parse_all_events_and_hits(
    projects_dir: Path,
) -> tuple[list[MessageEvent], list[LimitHit]]:
    """Single-pass scan: return both MessageEvents and raw LimitHits."""
    if not projects_dir.exists():
        return [], []
    all_events: list[MessageEvent] = []
    all_hits: list[LimitHit] = []
    for path in projects_dir.rglob("*.jsonl"):
        evs, hits = _parse_file(path)
        all_events.extend(evs)
        all_hits.extend(hits)
    all_events.sort(key=lambda e: e.timestamp)
    all_hits.sort(key=lambda h: h.timestamp)
    return all_events, all_hits


def aggregate_sessions(events: list[MessageEvent]) -> list[SessionAgg]:
    by_id: dict[str, SessionAgg] = {}
    model_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in events:
        agg = by_id.get(ev.session_id)
        if agg is None:
            agg = SessionAgg(
                session_id=ev.session_id,
                project=ev.project,
                cwd=ev.cwd,
                started_at=ev.timestamp,
                model=ev.model,
            )
            by_id[ev.session_id] = agg
        elif ev.timestamp < agg.started_at:
            agg.started_at = ev.timestamp

        agg.input_tokens += ev.input_tokens
        agg.output_tokens += ev.output_tokens
        agg.cache_create_tokens += ev.cache_create_tokens
        agg.cache_read_tokens += ev.cache_read_tokens
        agg.message_count += 1
        agg.models_used.add(ev.model)
        model_counts[ev.session_id][ev.model] += 1

    for sid, agg in by_id.items():
        if model_counts[sid]:
            agg.model = max(model_counts[sid].items(), key=lambda kv: kv[1])[0]
    return list(by_id.values())


def parse_all(projects_dir: Path) -> list[SessionAgg]:
    """Parse JSONL logs into session aggregates (kept for compatibility)."""
    return aggregate_sessions(parse_all_events(projects_dir))


def default_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"
