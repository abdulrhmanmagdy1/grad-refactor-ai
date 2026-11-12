"""Tests for the security/tracing middleware (NFR01, NFR02, observability)."""

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_responses_carry_request_id_timing_and_security_headers():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers["x-request-id"]
    float(res.headers["x-process-time-ms"])  # parseable milliseconds
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_well_formed_incoming_request_id_is_echoed():
    res = client.get("/health", headers={"X-Request-ID": "abc-123_ok.id"})
    assert res.headers["x-request-id"] == "abc-123_ok.id"


def test_malformed_incoming_request_id_is_replaced_with_uuid():
    res = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
    request_id = res.headers["x-request-id"]
    assert request_id != "bad id with spaces"
    assert len(request_id) == 32  # uuid4 hex
    assert request_id.isalnum()


def test_oversized_payload_is_rejected_with_tracing_headers():
    res = client.post(
        "/api/v1/analyze",
        content=b"x" * 200_000,
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 413
    assert "Payload too large" in res.json()["detail"]
    assert res.headers["x-request-id"]


def test_responses_carry_a_strict_content_security_policy():
    res = client.get("/health")
    policy = res.headers["content-security-policy"]

    # The client is served from the same origin and loads no third-party code.
    assert "default-src 'self'" in policy
    assert "script-src 'self'" in policy
    assert "object-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    # Monaco injects styles at runtime and boots its workers from blob URLs.
    assert "style-src 'self' 'unsafe-inline'" in policy
    assert "worker-src 'self' blob:" in policy
    assert res.headers["permissions-policy"].startswith("camera=()")


def test_request_ids_differ_between_requests():
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]
    assert first != second
