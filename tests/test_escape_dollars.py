import pytest
from app import escape_dollars


def test_escape_dollars_basic():
    text = "$199.9 million ... $12 million"
    expected = r"\$199.9 million ... \$12 million"
    assert escape_dollars(text) == expected


def test_escape_dollars_ranges():
    text = "ACV increased from $84,200 to $97,650 year-over-year."
    expected = r"ACV increased from \$84,200 to \$97,650 year-over-year."
    assert escape_dollars(text) == expected


def test_escape_dollars_idempotent():
    text = r"Already escaped \$100 and unescaped $200."
    expected = r"Already escaped \$100 and unescaped \$200."
    assert escape_dollars(text) == expected
    # Calling twice should produce the same result
    assert escape_dollars(expected) == expected


def test_escape_dollars_no_dollars():
    text = "Operating margin expanded from 14.2% to 17.6%."
    assert escape_dollars(text) == text


def test_escape_dollars_none_and_empty():
    assert escape_dollars("") == ""
    assert escape_dollars(None) is None
