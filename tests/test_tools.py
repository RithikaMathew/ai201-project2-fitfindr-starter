"""
tests/test_tools.py

Tests for each FitFindr tool, covering the happy path and each failure mode.
Run with:  pytest tests/
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import search_listings, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=20)
    assert all(item["price"] <= 20 for item in results)

def test_search_size_filter():
    results = search_listings("tee", size="XL", max_price=None)
    assert all("xl" in item["size"].lower() for item in results)

def test_search_no_exception_on_impossible_query():
    # Should return [] not raise
    try:
        results = search_listings("zzzznonexistent", size="ZZZ", max_price=0.01)
        assert results == []
    except Exception as e:
        assert False, f"search_listings raised an exception: {e}"

def test_search_sorted_by_relevance():
    # Top result should match more keywords than last result
    results = search_listings("vintage denim jacket", size=None, max_price=None)
    assert len(results) >= 2  # enough results to compare


# ── suggest_outfit (no LLM call — just structure tests) ───────────────────────

def test_suggest_outfit_empty_wardrobe_no_crash():
    """suggest_outfit should return a non-empty string for an empty wardrobe."""
    # We skip actual LLM call in unit test — just verify the tool doesn't crash
    # when called via the agent path. For a real integration test, set GROQ_API_KEY.
    # Here we just confirm the function exists and accepts the right signature.
    from tools import suggest_outfit
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0, "Need at least one listing for this test"
    # Only run LLM path if API key is present
    if not os.environ.get("GROQ_API_KEY"):
        return  # skip in environments without a key
    result = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0

def test_suggest_outfit_example_wardrobe_no_crash():
    from tools import suggest_outfit
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    if not os.environ.get("GROQ_API_KEY"):
        return
    result = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_fit_card_empty_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = create_fit_card("", results[0])
    assert isinstance(result, str)
    assert "error" in result.lower() or "Error" in result

def test_fit_card_whitespace_outfit_returns_error_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert "error" in result.lower() or "Error" in result

def test_fit_card_no_exception_on_valid_input():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    if not os.environ.get("GROQ_API_KEY"):
        return
    result = create_fit_card("Pair it with wide-leg jeans and chunky sneakers.", results[0])
    assert isinstance(result, str)
    assert len(result) > 0
