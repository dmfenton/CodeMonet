"""Tests for the /traces endpoint."""

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from code_monet.auth.rate_limit import rate_limiter


class TestTracesEndpoint:
    """Tests for POST /traces endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked tracing."""
        with patch("code_monet.routes.tracing.record_client_spans") as mock_record:
            mock_record.return_value = 1
            # Import app after patching
            from code_monet.main import app

            yield TestClient(app), mock_record

    @pytest.fixture(autouse=True)
    def reset_rate_limiter(self):
        """Reset rate limiter between tests."""
        rate_limiter.cleanup()
        yield
        rate_limiter.cleanup()

    def test_receive_traces_success(self, client):
        """Test successfully receiving spans."""
        test_client, mock_record = client
        payload = {
            "spans": [
                {
                    "traceId": "1-12345678-123456789012345678901234",
                    "spanId": "1234567890abcdef",
                    "name": "test.event",
                    "startTime": 1704067200000,
                    "endTime": 1704067200100,
                    "attributes": {"key": "value"},
                    "status": "ok",
                }
            ]
        }

        response = test_client.post("/traces", json=payload)

        assert response.status_code == 200
        assert response.json() == {"received": 1}
        mock_record.assert_called_once()

    def test_receive_traces_empty(self, client):
        """Test receiving empty spans list."""
        test_client, mock_record = client
        payload: dict[str, Any] = {"spans": []}

        response = test_client.post("/traces", json=payload)

        assert response.status_code == 200
        mock_record.assert_called_once_with([])

    def test_receive_traces_multiple_spans(self, client):
        """Test receiving multiple spans."""
        test_client, mock_record = client
        mock_record.return_value = 3
        payload = {
            "spans": [
                {
                    "traceId": "1-12345678-123456789012345678901234",
                    "spanId": "1234567890abcdef",
                    "name": "event.1",
                    "startTime": 1704067200000,
                },
                {
                    "traceId": "1-12345678-123456789012345678901234",
                    "spanId": "abcdef1234567890",
                    "name": "event.2",
                    "startTime": 1704067200100,
                },
                {
                    "traceId": "1-12345678-123456789012345678901234",
                    "spanId": "fedcba0987654321",
                    "name": "event.3",
                    "startTime": 1704067200200,
                    "status": "error",
                    "error": "Something failed",
                },
            ]
        }

        response = test_client.post("/traces", json=payload)

        assert response.status_code == 200
        assert response.json() == {"received": 3}

    def test_receive_traces_with_all_fields(self, client):
        """Test span with all optional fields."""
        test_client, _ = client
        payload = {
            "spans": [
                {
                    "traceId": "1-12345678-123456789012345678901234",
                    "spanId": "1234567890abcdef",
                    "parentSpanId": "fedcba0987654321",
                    "name": "child.span",
                    "startTime": 1704067200000,
                    "endTime": 1704067200500,
                    "attributes": {
                        "string_attr": "value",
                        "int_attr": 42,
                        "float_attr": 3.14,
                        "bool_attr": True,
                    },
                    "status": "ok",
                    "error": None,
                }
            ]
        }

        response = test_client.post("/traces", json=payload)

        assert response.status_code == 200

    def test_receive_traces_invalid_payload(self, client):
        """Test invalid payload returns 422."""
        test_client, _ = client

        response = test_client.post("/traces", json={"invalid": "payload"})

        assert response.status_code == 422

    def test_receive_traces_missing_required_fields(self, client):
        """Test span missing required fields returns 422."""
        test_client, _ = client
        payload = {
            "spans": [
                {
                    "name": "missing.ids",
                    # Missing traceId, spanId, startTime
                }
            ]
        }

        response = test_client.post("/traces", json=payload)

        assert response.status_code == 422


class TestTracesRateLimiting:
    """Tests for rate limiting on /traces endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked tracing."""
        with patch("code_monet.routes.tracing.record_client_spans") as mock_record:
            mock_record.return_value = 1
            from code_monet.main import app

            yield TestClient(app)

    @pytest.fixture(autouse=True)
    def reset_rate_limiter(self):
        """Reset rate limiter between tests."""
        # Clear all entries
        rate_limiter._requests.clear()
        yield
        rate_limiter._requests.clear()

    def test_rate_limit_allows_normal_traffic(self, client):
        """Test rate limit allows requests within limit."""
        payload = {
            "spans": [
                {
                    "traceId": "1-12345678-123456789012345678901234",
                    "spanId": "1234567890abcdef",
                    "name": "test.event",
                    "startTime": 1704067200000,
                }
            ]
        }

        # First request should succeed
        response = client.post("/traces", json=payload)
        assert response.status_code == 200

        # Several more requests should also succeed (under 60/min limit)
        for _ in range(10):
            response = client.post("/traces", json=payload)
            assert response.status_code == 200

    def test_rate_limit_blocks_excess_traffic(self, client):
        """Test rate limit blocks requests over limit."""
        payload = {
            "spans": [
                {
                    "traceId": "1-12345678-123456789012345678901234",
                    "spanId": "1234567890abcdef",
                    "name": "test.event",
                    "startTime": 1704067200000,
                }
            ]
        }

        # Make 60 requests (the limit)
        for _ in range(60):
            response = client.post("/traces", json=payload)
            assert response.status_code == 200

        # 61st request should be rate limited
        response = client.post("/traces", json=payload)
        assert response.status_code == 429
        assert response.json() == {"detail": "Too many requests"}
