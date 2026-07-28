"""Basic 認証とルーティングだけを確認する。Cosmos DB は差し替える。"""

import datetime

import pytest
from fastapi.testclient import TestClient

from diary_admin import cosmos, main

ENTRY = {"id": "entry-1", "userId": "U-test", "date": "2026-07-27", "content": "本文"}
CREDENTIALS = ("admin", "secret")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(cosmos, "list_entries", lambda month: [{"id": ENTRY["id"], "date": ENTRY["date"], "preview": "本文"}])
    monkeypatch.setattr(cosmos, "list_months", lambda: ["2026-07"])
    monkeypatch.setattr(cosmos, "read_entry", lambda entry_id: ENTRY if entry_id == ENTRY["id"] else None)
    return TestClient(main.app)


def test_requires_authentication(client: TestClient):
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("admin", "wrong")).status_code == 401


def test_index_lists_entries(client: TestClient):
    response = client.get("/", auth=CREDENTIALS)

    assert response.status_code == 200
    assert ENTRY["date"] in response.text


def test_detail_shows_content(client: TestClient):
    response = client.get(f"/entries/{ENTRY['id']}", auth=CREDENTIALS)

    assert response.status_code == 200
    assert ENTRY["content"] in response.text


def test_detail_returns_404_for_unknown_entry(client: TestClient):
    assert client.get("/entries/unknown", auth=CREDENTIALS).status_code == 404


def test_change_date_updates_entry_and_redirects(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[dict, datetime.date]] = []
    monkeypatch.setattr(cosmos, "change_date", lambda entry, new_date: calls.append((entry, new_date)))

    response = client.post(f"/entries/{ENTRY['id']}/date", data={"date": "2026-07-26"}, follow_redirects=False)

    assert response.status_code == 401  # 認証なしでは更新できない
    response = client.post(
        f"/entries/{ENTRY['id']}/date", data={"date": "2026-07-26"}, auth=CREDENTIALS, follow_redirects=False
    )
    assert response.status_code == 303
    assert calls == [(ENTRY, datetime.date(2026, 7, 26))]


def test_delete_removes_entry_and_redirects(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    deleted: list[dict] = []
    monkeypatch.setattr(cosmos, "delete_entry", deleted.append)

    response = client.post(f"/entries/{ENTRY['id']}/delete", auth=CREDENTIALS, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert deleted == [ENTRY]
