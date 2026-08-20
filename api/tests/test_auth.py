"""Auth-related tests: missing, malformed, and valid Bearer tokens."""
from __future__ import annotations


def test_health_does_not_require_auth(client):
    """``/health`` is public."""
    r = client.get("/health")
    assert r.status_code == 200


def test_root_does_not_require_auth(client):
    r = client.get("/")
    assert r.status_code == 200


def test_languages_requires_token(client):
    r = client.get("/api/v1/languages")
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "missing_authorization"


def test_languages_rejects_wrong_token(client):
    r = client.get(
        "/api/v1/languages",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "invalid_token"


def test_languages_rejects_non_bearer_scheme(client):
    r = client.get(
        "/api/v1/languages",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert r.status_code == 401


def test_languages_accepts_correct_token(client, auth_headers):
    r = client.get("/api/v1/languages", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    codes = [lang["code"] for lang in body["languages"]]
    assert codes == ["id", "en", "ar"]
