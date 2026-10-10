import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

import app as module
import claude_connector as connector

KEY = "a" * 40
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 50
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DATA", tmp_path)
    monkeypatch.setattr(module, "PUBLIC_URL", "https://cal.example")
    monkeypatch.setenv("ACTION_API_KEY", KEY)
    monkeypatch.setenv("CARBONATE_BRIDGE_PASSWORD", "test-secret")
    monkeypatch.delenv("ACTION_API_KEY_FILE", raising=False)
    monkeypatch.delenv("CARBONATE_BRIDGE_PASSWORD_FILE", raising=False)
    monkeypatch.setattr(module, "worker", lambda: None)
    connector.FAILURES.clear()
    (tmp_path / "auth.json").write_text("fake session")
    with TestClient(module.app, follow_redirects=False) as client:
        yield client


def register(client, **extra):
    response = client.post("/oauth/register", json={"redirect_uris": [CALLBACK], "client_name": "Claude", **extra})
    assert response.status_code == 201
    return response.json()


def authorize(client, client_id, key=KEY, **overrides):
    form = {"client_id": client_id, "redirect_uri": CALLBACK, "response_type": "code", "code_challenge": CHALLENGE,
            "code_challenge_method": "S256", "state": "xyz", "resource": "https://cal.example/mcp",
            "owner_key": key, "decision": "approve", **overrides}
    return client.post("/oauth/authorize", data=form)


def tokens(client):
    client_id = register(client)["client_id"]
    location = authorize(client, client_id).headers["location"]
    code = parse_qs(urlsplit(location).query)["code"][0]
    response = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                                 "redirect_uri": CALLBACK, "code_verifier": VERIFIER})
    assert response.status_code == 200
    return client_id, response.json()


def rpc(client, method, params=None, token=KEY):
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                           headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    return response.json()["result"]


def test_discovery_points_to_this_server(client):
    unauthorized = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert unauthorized.status_code == 401
    assert "https://cal.example/.well-known/oauth-protected-resource/mcp" in unauthorized.headers["www-authenticate"]
    resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == "https://cal.example/mcp"
    server = client.get("/.well-known/oauth-authorization-server").json()
    assert server["issuer"] == "https://cal.example"
    assert server["code_challenge_methods_supported"] == ["S256"]


def test_registration_rejects_foreign_redirects(client):
    for uri in ("https://evil.example/callback", "https://claude.ai/other", "http://evil.example/cb"):
        assert client.post("/oauth/register", json={"redirect_uris": [uri]}).status_code == 400
    assert register(client, redirect_uris=["http://localhost:33418/callback"])["redirect_uris"] == ["http://localhost:33418/callback"]


def test_full_oauth_flow_and_tool_call(client):
    client_id = register(client)["client_id"]
    page = client.get("/oauth/authorize", params={"client_id": client_id, "redirect_uri": CALLBACK, "response_type": "code",
                                                  "code_challenge": CHALLENGE, "code_challenge_method": "S256", "state": "xyz"})
    assert page.status_code == 200 and "ACTION_API_KEY" in page.text
    assert page.headers["x-frame-options"] == "DENY"
    _, issued = tokens(client)
    initialize = rpc(client, "initialize", {"protocolVersion": "2025-06-18"}, issued["access_token"])
    assert initialize["protocolVersion"] == "2025-06-18"
    assert len(rpc(client, "tools/list", token=issued["access_token"])["tools"]) == 11
    context = rpc(client, "tools/call", {"name": "getCalendarContext", "arguments": {}}, issued["access_token"])
    assert not context["isError"] and context["structuredContent"]["timezone"] == "Europe/Helsinki"


def test_wrong_key_and_lockout(client):
    client_id = register(client)["client_id"]
    for _ in range(5):
        assert authorize(client, client_id, key="b" * 40).status_code == 401
    assert authorize(client, client_id).status_code == 429


def test_deny_and_bad_pkce(client):
    client_id = register(client)["client_id"]
    denied = authorize(client, client_id, decision="deny").headers["location"]
    assert parse_qs(urlsplit(denied).query) == {"error": ["access_denied"], "state": ["xyz"], "iss": ["https://cal.example"]}
    code = parse_qs(urlsplit(authorize(client, client_id).headers["location"]).query)["code"][0]
    bad = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                            "redirect_uri": CALLBACK, "code_verifier": "w" * 50})
    assert bad.status_code == 400
    # The code was consumed by the failed attempt and cannot be replayed.
    again = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                              "redirect_uri": CALLBACK, "code_verifier": VERIFIER})
    assert again.status_code == 400


def test_refresh_rotates_and_key_rotation_revokes(client, monkeypatch):
    client_id, issued = tokens(client)
    refreshed = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": issued["refresh_token"], "client_id": client_id})
    assert refreshed.status_code == 200
    reused = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": issued["refresh_token"], "client_id": client_id})
    assert reused.status_code == 400
    access = refreshed.json()["access_token"]
    assert rpc(client, "ping", token=access) == {}
    monkeypatch.setenv("ACTION_API_KEY", "c" * 40)
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={"Authorization": "Bearer " + access})
    assert response.status_code == 401 and 'error="invalid_token"' in response.headers["www-authenticate"]


def test_confidential_client_requires_secret(client):
    registered = register(client, token_endpoint_auth_method="client_secret_post")
    code = parse_qs(urlsplit(authorize(client, registered["client_id"]).headers["location"]).query)["code"][0]
    form = {"grant_type": "authorization_code", "code": code, "client_id": registered["client_id"], "redirect_uri": CALLBACK, "code_verifier": VERIFIER}
    assert client.post("/oauth/token", data=form).status_code == 401
    assert client.post("/oauth/token", data={**form, "client_secret": registered["client_secret"]}).status_code == 200


def test_tools_queue_events_and_reject_bad_arguments(client):
    created = rpc(client, "tools/call", {"name": "createCalendarEvent", "arguments": {"title": "School", "start": "2026-10-07T09:45:00+03:00"}})
    assert not created["isError"] and created["structuredContent"]["state"] == "pending"
    assert created["structuredContent"]["event"]["end"] == "2026-10-07T07:45:00Z"
    for name, arguments in [("createCalendarEvent", {"title": "x", "start": "2026-10-07T09:45:00+03:00", "attendees": ["a@b.c"]}),
                            ("createCalendarEvent", {"title": "x", "start": "2026-10-07T09:45:00"}),
                            ("getEventStatus", {"job_id": "../etc"}),
                            ("deleteCalendarEvent", {"uid": "x", "scope": "series"}),
                            ("noSuchTool", {})]:
        assert rpc(client, "tools/call", {"name": name, "arguments": arguments})["isError"]
    listed = rpc(client, "tools/call", {"name": "listCalendars", "arguments": {}})
    assert listed["structuredContent"]["state"] == "pending"


def test_wait_for_stops_at_budget():
    clock = [0.0]
    states = iter(["pending", "pending", "verified"])
    value = connector.wait_for(lambda: {"state": next(states), "poll_after_seconds": 3},
                               budget=24, sleep=lambda s: clock.__setitem__(0, clock[0] + s), clock=lambda: clock[0])
    assert value["state"] == "verified" and clock[0] == 6
