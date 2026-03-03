"""
Tests for _extract_positions_from_text in resume_parser.
Covers the fix that filters sentence-like garbage lines (ending in punctuation,
containing digits, 'lead' as substring) so real titles like
'Business Efficiency Analyst' are returned correctly.
"""
import pytest
from src.libs.resume_parser import _extract_positions_from_text


def test_extracts_clean_titles():
    text = """
Business Efficiency Analyst
Logistics Manager
Transportation Manager
Supply Chain Director
"""
    result = _extract_positions_from_text(text)
    assert "Business Efficiency Analyst" in result
    assert "Logistics Manager" in result
    assert "Transportation Manager" in result


def test_filters_sentence_ending_with_period():
    text = """
Leading To A 16% Reduction In Organizational Overtime.
Improving Average Lead Times To Under 1.7 Days.
Logistics Manager
"""
    result = _extract_positions_from_text(text)
    assert not any("Reduction" in r for r in result)
    assert not any("Lead Times" in r for r in result)
    assert "Logistics Manager" in result


def test_filters_lines_with_digits():
    text = """
Increased revenue by 40% annually
Logistics Manager
Sr. Supply Chain Manager
"""
    result = _extract_positions_from_text(text)
    assert not any("40%" in r for r in result)
    assert "Logistics Manager" in result


def test_lead_as_substring_not_matched():
    """'leading' (substring) should not match, but 'Lead' as a standalone word is allowed."""
    text = """
Leading a team of engineers
Supply Chain Lead
"""
    result = _extract_positions_from_text(text)
    # "Leading a team of engineers" has 5 words and "leading" contains "lead"
    # but the whole-word regex should not match "lead" inside "leading"
    assert not any("Leading a team" in r for r in result)
    # "Supply Chain Lead" is a valid title and should match
    assert "Supply Chain Lead" in result


def test_empty_text_returns_empty():
    assert _extract_positions_from_text("") == []


def test_cap_at_eight():
    text = "\n".join([
        "Supply Chain Manager",
        "Logistics Manager",
        "Operations Manager",
        "Procurement Manager",
        "Inventory Manager",
        "Transportation Manager",
        "Warehouse Manager",
        "Distribution Manager",
        "Fleet Manager",
        "Export Coordinator",
    ])
    result = _extract_positions_from_text(text)
    assert len(result) <= 8


def test_business_efficiency_analyst_not_dropped_by_cap():
    """Regression: before fix, sentence lines consumed slots and pushed out real titles."""
    text = """
Business Efficiency Analyst
Logistics Manager
Transportation Manager
Supply Chain Manager
Operations Manager
Procurement Manager
"""
    result = _extract_positions_from_text(text)
    assert "Business Efficiency Analyst" in result
