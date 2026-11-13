import app as app_module


def test_health_endpoint_returns_ok():
    client = app_module.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "app": "Scholar Tracker"}


def test_parent_calendar_is_read_only_and_respects_authentication():
    client = app_module.app.test_client()
    response = client.get("/parents/calendar")
    if response.status_code == 302:
        assert "/parents/login" in response.headers["Location"]
        return
    assert response.status_code == 200
    assert b"School calendar for parents" in response.data
    assert b"read-only calendar view" in response.data
    assert b"admission_no" not in response.data


def test_security_headers_are_present():
    client = app_module.app.test_client()
    response = client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
