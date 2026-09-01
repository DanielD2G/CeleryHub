from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestAlertChannels:
    async def test_crud_cycle(self, client):
        # create
        resp = await client.post("/api/alerts/channels", json={
            "name": "ops", "kind": "webhook",
            "config": {"url": "http://example.invalid/hook"},
            "rules": {"workflow_failed": {"enabled": True}},
        })
        assert resp.status_code == 201, resp.text
        ch = resp.json()
        assert ch["kind"] == "webhook" and ch["rules"]["workflow_failed"]["enabled"]

        # list
        resp = await client.get("/api/alerts/channels")
        assert [c["id"] for c in resp.json()] == [ch["id"]]

        # update
        resp = await client.put(f"/api/alerts/channels/{ch['id']}", json={
            "name": "ops2", "kind": "webhook",
            "config": {"url": "http://example.invalid/hook2"},
            "enabled": False, "rules": {},
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "ops2"
        assert resp.json()["enabled"] is False

        # delete
        resp = await client.delete(f"/api/alerts/channels/{ch['id']}")
        assert resp.status_code == 204
        assert (await client.get("/api/alerts/channels")).json() == []

    async def test_validation(self, client):
        r = await client.post("/api/alerts/channels", json={
            "name": "x", "kind": "smoke-signal", "config": {}, "rules": {},
        })
        assert r.status_code == 400
        r = await client.post("/api/alerts/channels", json={
            "name": "x", "kind": "webhook", "config": {}, "rules": {},
        })
        assert r.status_code == 400  # missing url
        r = await client.post("/api/alerts/channels", json={
            "name": "x", "kind": "webhook",
            "config": {"url": "http://a"}, "rules": {"nope": {"enabled": True}},
        })
        assert r.status_code == 400  # unknown rule

    async def test_rules_listing(self, client):
        resp = await client.get("/api/alerts/rules")
        assert "workflow_failed" in resp.json()
        assert "dead_mans_switch" in resp.json()

    async def test_test_fire(self, client):
        resp = await client.post("/api/alerts/channels", json={
            "name": "t", "kind": "webhook",
            "config": {"url": "http://example.invalid/hook"}, "rules": {},
        })
        ch_id = resp.json()["id"]
        with patch(
            "celery_gateway.routers.alerts._deliver",
            new=AsyncMock(return_value=(True, None)),
        ):
            resp = await client.post(f"/api/alerts/channels/{ch_id}/test")
        assert resp.json() == {"delivered": True, "error": None}
