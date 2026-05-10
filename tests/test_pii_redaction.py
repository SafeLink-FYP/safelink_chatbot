"""
Audit B6 — PII redaction broadened to:
- Pakistani landlines (021/042/051/...).
- Unhyphenated 13-digit CNICs gated by a context word so we don't redact
  arbitrary 13-digit runs (timestamps, serial numbers, etc.).

The existing hyphenated CNIC + Pakistani mobile + email patterns still apply.
"""
import pytest

from nlp.preprocessor import TextPreprocessor


@pytest.fixture(scope="module")
def preprocessor():
    return TextPreprocessor(anonymize_pii=True)


def _process(preprocessor: TextPreprocessor, text: str) -> str:
    out, _meta = preprocessor.preprocess(text)
    return out


def test_pakistani_mobile_redacted(preprocessor):
    out = _process(preprocessor, "call me at 0321-1234567 now")
    assert "0321-1234567" not in out
    assert "[REDACTED" in out


def test_pakistani_landline_redacted(preprocessor):
    out = _process(preprocessor, "PDMA Punjab is at 042-99205316 for help")
    assert "042-99205316" not in out
    assert "[REDACTED" in out


def test_hyphenated_cnic_redacted(preprocessor):
    out = _process(preprocessor, "my cnic is 12345-1234567-1 thanks")
    assert "12345-1234567-1" not in out


def test_unhyphenated_cnic_with_context_redacted(preprocessor):
    out = _process(preprocessor, "my cnic 1234512345671 was lost")
    assert "1234512345671" not in out


def test_random_13_digit_string_without_context_not_redacted(preprocessor):
    """
    A 13-digit number without any CNIC context word must NOT be redacted —
    that pattern is reserved for ID cards. Common false-positive vectors:
    timestamps, package barcodes, serial numbers.
    """
    text = "the order id is 1234567890123 in our system"
    out = _process(preprocessor, text)
    assert "1234567890123" in out
    # Phone-shape regexes shouldn't accidentally swallow it either.
    assert "[REDACTED_CNIC" not in out


def test_email_still_redacted(preprocessor):
    out = _process(preprocessor, "reach me at user@example.com")
    assert "user@example.com" not in out


def test_no_pii_no_redaction(preprocessor):
    out = _process(preprocessor, "what should i do during an earthquake")
    assert "REDACTED" not in out
