"""Tests for structured logging configuration."""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from code_monet.logging_config import (
    ErrorFilter,
    StructuredFormatter,
    configure_logging,
)


class TestStructuredFormatter:
    """Tests for StructuredFormatter JSON output."""

    @pytest.fixture
    def formatter(self) -> StructuredFormatter:
        """Create a formatter instance."""
        return StructuredFormatter()

    @pytest.fixture
    def log_record(self) -> logging.LogRecord:
        """Create a basic log record."""
        return logging.LogRecord(
            name="code_monet.auth.routes",
            level=logging.INFO,
            pathname="routes.py",
            lineno=42,
            msg="User signed in",
            args=(),
            exc_info=None,
        )

    def test_basic_json_output(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that output is valid JSON with required fields."""
        output = formatter.format(log_record)
        data = json.loads(output)

        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["logger"] == "code_monet.auth.routes"
        assert data["message"] == "User signed in"
        assert "category" in data

    def test_category_detection_auth(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test category detection for auth loggers."""
        log_record.name = "code_monet.auth.routes"
        output = formatter.format(log_record)
        data = json.loads(output)
        assert data["category"] == "auth"

    def test_category_detection_agent(self, formatter: StructuredFormatter) -> None:
        """Test category detection for agent loggers."""
        record = logging.LogRecord(
            name="code_monet.agent.processor",
            level=logging.INFO,
            pathname="processor.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["category"] == "agent"

    def test_category_detection_websocket(self, formatter: StructuredFormatter) -> None:
        """Test category detection for websocket loggers."""
        for logger_name in ["code_monet.connections", "code_monet.user_handlers"]:
            record = logging.LogRecord(
                name=logger_name,
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["category"] == "websocket", f"Failed for {logger_name}"

    def test_category_detection_workspace(self, formatter: StructuredFormatter) -> None:
        """Test category detection for workspace loggers."""
        for logger_name in [
            "code_monet.workspace_state",
            "code_monet.workspace",
            "code_monet.registry",
        ]:
            record = logging.LogRecord(
                name=logger_name,
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["category"] == "workspace", f"Failed for {logger_name}"

    def test_category_detection_http(self, formatter: StructuredFormatter) -> None:
        """Test category detection for HTTP loggers."""
        for logger_name in ["code_monet.main", "code_monet.routes", "uvicorn"]:
            record = logging.LogRecord(
                name=logger_name,
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["category"] == "http", f"Failed for {logger_name}"

    def test_category_detection_system(self, formatter: StructuredFormatter) -> None:
        """Test category detection for system loggers."""
        for logger_name in [
            "code_monet.shutdown",
            "code_monet.config",
            "code_monet.tracing",
        ]:
            record = logging.LogRecord(
                name=logger_name,
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["category"] == "system", f"Failed for {logger_name}"

    def test_category_detection_unknown(self, formatter: StructuredFormatter) -> None:
        """Test category defaults to system for unknown loggers."""
        record = logging.LogRecord(
            name="unknown.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["category"] == "system"

    def test_user_id_included(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that user_id is included when present."""
        log_record.user_id = 42
        output = formatter.format(log_record)
        data = json.loads(output)
        assert data["user_id"] == 42

    def test_user_id_excluded_when_none(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that user_id is not included when None."""
        log_record.user_id = None
        output = formatter.format(log_record)
        data = json.loads(output)
        assert "user_id" not in data

    def test_user_id_excluded_when_missing(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that user_id is not included when not set."""
        output = formatter.format(log_record)
        data = json.loads(output)
        assert "user_id" not in data

    def test_extra_fields_serializable(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that serializable extra fields are included."""
        log_record.email = "user@example.com"
        log_record.method = "magic_link"
        output = formatter.format(log_record)
        data = json.loads(output)
        assert "extra" in data
        assert data["extra"]["email"] == "user@example.com"
        assert data["extra"]["method"] == "magic_link"

    def test_extra_fields_non_serializable(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that non-serializable extra fields are converted to string."""
        log_record.custom_obj = object()
        output = formatter.format(log_record)
        data = json.loads(output)
        assert "extra" in data
        assert "custom_obj" in data["extra"]
        assert isinstance(data["extra"]["custom_obj"], str)

    def test_exception_info(self, formatter: StructuredFormatter) -> None:
        """Test that exception info is included."""
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "Test error" in data["exception"]

    def test_trace_id_from_opentelemetry(self, formatter: StructuredFormatter) -> None:
        """Test trace_id extraction from OpenTelemetry span."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_context = MagicMock()
        mock_context.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        mock_span.get_span_context.return_value = mock_context

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert "trace_id" in data
            assert data["trace_id"].startswith("1-")

    def test_trace_id_not_recording(self, formatter: StructuredFormatter) -> None:
        """Test that trace_id is not included when span is not recording."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert "trace_id" not in data

    def test_trace_id_from_record(
        self, formatter: StructuredFormatter, log_record: logging.LogRecord
    ) -> None:
        """Test that trace_id from record takes precedence."""
        log_record.trace_id = "custom-trace-id"
        output = formatter.format(log_record)
        data = json.loads(output)
        assert data["trace_id"] == "custom-trace-id"


class TestErrorFilter:
    """Tests for ErrorFilter."""

    @pytest.fixture
    def error_filter(self) -> ErrorFilter:
        """Create an ErrorFilter instance."""
        return ErrorFilter()

    def test_allows_error(self, error_filter: ErrorFilter) -> None:
        """Test that ERROR level logs are allowed."""
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error",
            args=(),
            exc_info=None,
        )
        assert error_filter.filter(record) is True

    def test_allows_critical(self, error_filter: ErrorFilter) -> None:
        """Test that CRITICAL level logs are allowed."""
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="test.py",
            lineno=1,
            msg="Critical",
            args=(),
            exc_info=None,
        )
        assert error_filter.filter(record) is True

    def test_blocks_warning(self, error_filter: ErrorFilter) -> None:
        """Test that WARNING level logs are blocked."""
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning",
            args=(),
            exc_info=None,
        )
        assert error_filter.filter(record) is False

    def test_blocks_info(self, error_filter: ErrorFilter) -> None:
        """Test that INFO level logs are blocked."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Info",
            args=(),
            exc_info=None,
        )
        assert error_filter.filter(record) is False

    def test_blocks_debug(self, error_filter: ErrorFilter) -> None:
        """Test that DEBUG level logs are blocked."""
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="Debug",
            args=(),
            exc_info=None,
        )
        assert error_filter.filter(record) is False


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_json_format_output(self) -> None:
        """Test that JSON format produces valid JSON."""
        output = StringIO()
        configure_logging(json_format=True, log_level=logging.INFO, stream=output)

        logger = logging.getLogger("test.json")
        logger.info("Test message")

        output.seek(0)
        content = output.read()
        assert content.strip()  # Not empty
        data = json.loads(content.strip())
        assert data["message"] == "Test message"

    def test_plain_format_output(self) -> None:
        """Test that plain format produces human-readable output."""
        output = StringIO()
        configure_logging(json_format=False, log_level=logging.INFO, stream=output)

        logger = logging.getLogger("test.plain")
        logger.info("Test message")

        output.seek(0)
        content = output.read()
        assert "Test message" in content
        assert "INFO" in content
        # Should not be JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(content.strip())

    def test_log_level_filtering(self) -> None:
        """Test that log level filtering works."""
        output = StringIO()
        configure_logging(json_format=False, log_level=logging.WARNING, stream=output)

        logger = logging.getLogger("test.level")
        logger.info("Info message")
        logger.warning("Warning message")

        output.seek(0)
        content = output.read()
        assert "Info message" not in content
        assert "Warning message" in content

    def test_noisy_loggers_silenced(self) -> None:
        """Test that noisy loggers are silenced."""
        configure_logging(json_format=False, log_level=logging.INFO)

        noisy_loggers = [
            "watchfiles",
            "httpcore",
            "httpx",
            "anthropic",
            "PIL",
            "urllib3",
            "botocore",
            "boto3",
        ]

        for name in noisy_loggers:
            logger = logging.getLogger(name)
            assert logger.level >= logging.WARNING, f"{name} should be silenced"
