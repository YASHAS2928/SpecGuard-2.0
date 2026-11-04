"""scripts/seed_demo.py: idempotent RQ-014 seed through the real API."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from scripts import seed_demo


def test_seed_creates_rq_014_once_and_is_idempotent(client: TestClient) -> None:
    existing = {r["code"] for r in client.get("/requirements").json()}
    first = seed_demo.seed(client)
    second = seed_demo.seed(client)
    assert first == ("already present" if seed_demo.CODE in existing else "created")
    assert second == "already present"
    matches = [r for r in client.get("/requirements").json() if r["code"] == seed_demo.CODE]
    assert len(matches) == 1


def test_seed_creates_the_expected_unapproved_requirement(client: TestClient) -> None:
    seed_demo.seed(client)
    requirement = next(r for r in client.get("/requirements").json() if r["code"] == seed_demo.CODE)
    assert requirement["status"] == "DRAFT" and requirement["latest_version"] == 1
    version = requirement["versions"][0]
    assert version["policy_ids"] == ["POL-OT-01@v1", "POL-MEAL-02@v1", "POL-DATE-03@v1"]
    assert version["author"] == "asha.ba" and version["text"] == seed_demo.TEXT
    assert client.get(f"/requirement-versions/{version['id']}/specs").json() == []  # nothing analysed or approved


def test_a_conflict_from_a_concurrent_seed_counts_as_already_present() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(409, json={"error": {"code": "CONFLICT"}})

    with httpx.Client(base_url="http://backend.test", transport=httpx.MockTransport(handler)) as client:
        assert seed_demo.seed(client) == "already present"


def test_an_existing_requirement_is_never_posted_again() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json=[{"code": seed_demo.CODE}])

    with httpx.Client(base_url="http://backend.test", transport=httpx.MockTransport(handler)) as client:
        assert seed_demo.seed(client) == "already present"
    assert calls == ["GET"]


def test_other_http_errors_are_not_swallowed() -> None:
    handler = lambda request: httpx.Response(503, json={})  # noqa: E731
    with httpx.Client(base_url="http://backend.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            seed_demo.seed(client)
