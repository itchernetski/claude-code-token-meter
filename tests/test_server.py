"""Smoke tests for the FastAPI surface — focuses on the manual quota wiring.

We don't replay full JSONL fixtures here — `test_parser.py` covers the data
path. This file pins the HTTP contract so future refactors of the response
shape don't silently break the frontend.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_code_token_meter.server import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # Empty projects dir → empty data, but the surface still exists.
    projects = tmp_path / "projects"
    projects.mkdir()
    cfg = tmp_path / "config.json"
    app = create_app(projects_dir=projects, config_path=cfg)
    return TestClient(app)


def test_get_config_defaults_to_nulls(client: TestClient) -> None:
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == {"quota_5h": None, "quota_weekly": None}


def test_post_config_persists(client: TestClient, tmp_path: Path) -> None:
    r = client.post(
        "/api/config",
        json={"quota_5h": "6000000", "quota_weekly": 200_000_000},
    )
    assert r.status_code == 200
    assert r.json() == {"quota_5h": 6_000_000, "quota_weekly": 200_000_000}

    # Round-trip via GET
    r2 = client.get("/api/config")
    assert r2.json() == {"quota_5h": 6_000_000, "quota_weekly": 200_000_000}


def test_post_config_zero_clears_field(client: TestClient) -> None:
    client.post("/api/config", json={"quota_5h": 6_000_000})
    r = client.post("/api/config", json={"quota_5h": 0, "quota_weekly": None})
    assert r.json() == {"quota_5h": None, "quota_weekly": None}


def test_stats_includes_quota_field(client: TestClient) -> None:
    r = client.get("/api/stats?days=7")
    assert r.status_code == 200
    body = r.json()
    assert "quota" in body
    assert body["quota"] == {"quota_5h": None, "quota_weekly": None}


def test_stats_query_param_overrides_saved_quota(client: TestClient) -> None:
    client.post("/api/config", json={"quota_5h": 5_000_000})
    r = client.get("/api/stats?days=7&quota_5h=9000000")
    body = r.json()
    assert body["quota"]["quota_5h"] == 9_000_000


def test_stats_query_param_partial_override(client: TestClient) -> None:
    """Overriding just one field keeps the other from saved config."""
    client.post(
        "/api/config",
        json={"quota_5h": 5_000_000, "quota_weekly": 200_000_000},
    )
    r = client.get("/api/stats?days=7&quota_weekly=300000000")
    body = r.json()
    assert body["quota"] == {
        "quota_5h": 5_000_000,
        "quota_weekly": 300_000_000,
    }


def test_burnrate_endpoint_includes_quota(client: TestClient) -> None:
    client.post("/api/config", json={"quota_5h": 6_000_000})
    r = client.get("/api/burnrate")
    body = r.json()
    assert body["quota"]["quota_5h"] == 6_000_000


def test_post_config_writes_to_disk(client: TestClient, tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    client.post("/api/config", json={"quota_5h": 7_000_000})
    assert cfg_path.exists()
    assert json.loads(cfg_path.read_text()) == {
        "quota_5h": 7_000_000,
        "quota_weekly": None,
    }


def test_index_serves_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "CC Token Meter" in r.text
