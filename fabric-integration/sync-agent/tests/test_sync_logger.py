"""Unit tests for FinOps Sync Agent Logger and Secret Redaction."""

import logging

from sync_logger import TokenRedactionFilter, setup_logger


def test_token_redaction_filter():
    filt = TokenRedactionFilter()

    # Test Bearer token scrubbing
    record1 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Connecting with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz123 to endpoint",
        args=(),
        exc_info=None,
    )
    filt.filter(record1)
    assert "Bearer ***REDACTED***" in record1.msg
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in record1.msg

    # Test client_secret scrubbing
    record2 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=2,
        msg='Setting configuration {"client_secret": "my-secret-pw-99"}',
        args=(),
        exc_info=None,
    )
    filt.filter(record2)
    assert "my-secret-pw-99" not in record2.msg
    assert "***REDACTED***" in record2.msg


def test_setup_logger():
    logger = setup_logger("test_finops_logger", verbose=True)
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) > 0
    assert any(isinstance(f, TokenRedactionFilter) for f in logger.handlers[0].filters)
