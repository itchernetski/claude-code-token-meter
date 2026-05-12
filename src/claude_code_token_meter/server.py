from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import __version__
from . import config as user_config
from .aggregator import (
    build_stats,
    burn_rate,
    calibrate_quota,
    filter_by_range,
    filter_events_by_range,
    range_from_days,
    snapshot_at,
)
from .detector import LimitEvent, cluster_hits
from .parser import (
    MessageEvent,
    SessionAgg,
    aggregate_sessions,
    default_projects_dir,
    parse_all_events_and_hits,
)
from .session_detail import analyze_session
from .storage import default_db_path, load_recent, upsert_events

PACKAGE_DIR = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


class SessionCache:
    def __init__(self, projects_dir: Path, db_path: Path | None = None):
        self.projects_dir = projects_dir
        self.db_path = db_path or default_db_path()
        self._events: list[MessageEvent] = []
        self._sessions: list[SessionAgg] = []
        self._limit_events: list[LimitEvent] = []
        self._loaded_at: datetime | None = None
        self._parse_seconds: float = 0.0
        self._inserted_hits: int = 0
        self._lock = Lock()

    def load(self) -> None:
        with self._lock:
            t0 = time.perf_counter()
            self._events, hits = parse_all_events_and_hits(self.projects_dir)
            self._sessions = aggregate_sessions(self._events)
            self._limit_events = cluster_hits(hits)

            # Capture burn-rate snapshot at the exact moment of each hit and
            # persist. Storage is idempotent on (ts_iso, reset_text) so this
            # is safe to call on every refresh.
            snapshots: dict[str, dict] = {}
            for ev in self._limit_events:
                snap = snapshot_at(self._events, ev.started_at)
                key = f"{ev.started_at.astimezone(timezone.utc).isoformat()}|{ev.reset_text}"
                snapshots[key] = snap
            try:
                self._inserted_hits = upsert_events(
                    self.db_path, self._limit_events, snapshots
                )
            except Exception:
                # Storage failures must not break the dashboard.
                self._inserted_hits = 0

            self._parse_seconds = time.perf_counter() - t0
            self._loaded_at = datetime.now(timezone.utc)

    @property
    def sessions(self) -> list[SessionAgg]:
        if self._loaded_at is None:
            self.load()
        return self._sessions

    @property
    def events(self) -> list[MessageEvent]:
        if self._loaded_at is None:
            self.load()
        return self._events

    @property
    def limit_events(self) -> list[LimitEvent]:
        if self._loaded_at is None:
            self.load()
        return self._limit_events

    def calibration(self) -> dict:
        try:
            rows = load_recent(self.db_path)
        except Exception:
            rows = []
        return calibrate_quota(rows)

    def info(self) -> dict:
        return {
            "projects_dir": str(self.projects_dir),
            "db_path": str(self.db_path),
            "sessions_total": len(self._sessions),
            "events_total": len(self._events),
            "limit_events_total": len(self._limit_events),
            "loaded_at": self._loaded_at.isoformat() if self._loaded_at else None,
            "parse_seconds": round(self._parse_seconds, 3),
            "version": __version__,
        }


def create_app(
    projects_dir: Path | None = None,
    config_path: Path | None = None,
) -> FastAPI:
    cache = SessionCache(projects_dir or default_projects_dir())
    cfg_path = config_path or user_config.default_config_path()
    app = FastAPI(title="claude-code-token-meter", version=__version__)
    app.state.cache = cache
    app.state.config_path = cfg_path
    app.mount(
        "/static",
        StaticFiles(directory=str(PACKAGE_DIR / "static")),
        name="static",
    )

    @app.on_event("startup")
    def _warm_cache() -> None:
        cache.load()

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {"info": cache.info()},
        )

    def _resolve_quota(
        quota_5h: int | None, quota_weekly: int | None
    ) -> dict:
        base = user_config.load(app.state.config_path)
        merged = user_config.merge_overrides(base, quota_5h, quota_weekly)
        return merged.to_dict()

    @app.get("/api/stats")
    def api_stats(
        days: float | None = Query(default=7, ge=0.04, le=365),
        start: str | None = Query(default=None),
        end: str | None = Query(default=None),
        quota_5h: int | None = Query(default=None, ge=1),
        quota_weekly: int | None = Query(default=None, ge=1),
    ):
        if start or end:
            try:
                start_dt = (
                    datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
                    if start
                    else datetime.fromtimestamp(0, tz=timezone.utc)
                )
                end_dt = (
                    datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
                    if end
                    else datetime.now(timezone.utc)
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Bad date: {e}")
        else:
            start_dt, end_dt = range_from_days(days or 7)

        filtered = filter_by_range(cache.sessions, start_dt, end_dt)
        filtered_events = filter_events_by_range(cache.events, start_dt, end_dt)
        stats = build_stats(filtered, filtered_events)
        stats["range"] = {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "days": (end_dt - start_dt).total_seconds() / 86400,
        }
        stats["burn_rate"] = burn_rate(cache.events)
        stats["calibration"] = cache.calibration()
        stats["quota"] = _resolve_quota(quota_5h, quota_weekly)
        stats["meta"] = cache.info()
        return stats

    @app.get("/api/burnrate")
    def api_burn_rate(
        quota_5h: int | None = Query(default=None, ge=1),
        quota_weekly: int | None = Query(default=None, ge=1),
    ):
        return {
            "burn_rate": burn_rate(cache.events),
            "calibration": cache.calibration(),
            "quota": _resolve_quota(quota_5h, quota_weekly),
            "meta": cache.info(),
        }

    @app.get("/session/{session_id}", response_class=HTMLResponse)
    def session_page(request: Request, session_id: str):
        detail = analyze_session(cache.projects_dir, session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return TEMPLATES.TemplateResponse(
            request,
            "session.html",
            {"detail": detail, "info": cache.info()},
        )

    @app.get("/api/session/{session_id}")
    def api_session(session_id: str):
        detail = analyze_session(cache.projects_dir, session_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return detail

    @app.post("/api/refresh")
    def api_refresh():
        cache.load()
        return cache.info()

    @app.get("/api/config")
    def api_get_config():
        return user_config.load(app.state.config_path).to_dict()

    @app.post("/api/config")
    def api_set_config(payload: dict = Body(default_factory=dict)):
        cfg = user_config.QuotaConfig(
            quota_5h=user_config._coerce_positive_int(payload.get("quota_5h")),
            quota_weekly=user_config._coerce_positive_int(
                payload.get("quota_weekly")
            ),
        )
        user_config.save(cfg, app.state.config_path)
        return cfg.to_dict()

    return app
