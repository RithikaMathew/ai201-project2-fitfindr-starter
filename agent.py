"""
agent.py

The FitFindr planning loop.
"""

import re
import os

from dotenv import load_dotenv
from groq import Groq

from tools import (
    search_listings,
    search_listings_relaxed,
    suggest_outfit,
    create_fit_card,
    price_comparison,
)

load_dotenv()


# ── simple logger ─────────────────────────────────────────────────────────────

def _log(msg: str):
    print(f"\033[33m[AGENT]\033[0m {msg}")


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "price_verdict": None,
        "search_relaxed_note": None,   # set if fallback retry loosened constraints
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.
    """
    price_match = re.search(
        r"(?:under|less than|max|up to)?\s*\$?\s*(\d+(?:\.\d+)?)\s*(?:dollars?)?",
        query,
        re.IGNORECASE,
    )
    max_price = float(price_match.group(1)) if price_match else None

    size_match = re.search(
        r"\b(?:size\s+)?([xX]{0,2}[sSlLmM](?:/[sSlLmM])?|[xX][sSlL]|XXL|XL|XS)\b",
        query,
    )
    size = size_match.group(1).upper() if size_match else None

    description = query
    if price_match:
        description = description[:price_match.start()] + description[price_match.end():]
    if size_match:
        description = description[:size_match.start()] + description[size_match.end():]
    for filler in [
        r"\bunder\b", r"\bless than\b", r"\bmax\b", r"\bup to\b",
        r"\bsize\b", r"\bi(?:'m)? looking for\b", r"\bfor\b",
        r"\ba\b", r"\ban\b", r"\bthe\b",
    ]:
        description = re.sub(filler, " ", description, flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", description).strip(" ,.")

    return {
        "description": description or query,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop and returns
    the completed session dict.

    Steps:
      1. Parse query
      2. search_listings() — with fallback retry (stretch feature)
      3. price_comparison() on top result (stretch feature)
      4. suggest_outfit()
      5. create_fit_card()
    """
    _log(f"run_agent started — query={repr(query)}")

    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query
    parsed = _parse_query(query)
    session["parsed"] = parsed
    _log(f"parsed → description={repr(parsed['description'])}, size={parsed['size']}, max_price={parsed['max_price']}")

    # Step 3: Search listings with fallback retry (stretch feature)
    results, relaxed_note = search_listings_relaxed(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results
    session["search_relaxed_note"] = relaxed_note if relaxed_note else None

    # Early exit if no results even after fallback
    if not results:
        size_note = f" in size {parsed['size']}" if parsed["size"] else ""
        price_note = f" under ${parsed['max_price']:.0f}" if parsed["max_price"] else ""
        session["error"] = (
            f"No listings found for \"{parsed['description']}\"{size_note}{price_note}. "
            "Try broadening your search — remove the size filter, raise the price limit, "
            "or use different keywords."
        )
        _log("run_agent → early exit (no results after fallback)")
        return session

    # Step 4: Select top result
    session["selected_item"] = results[0]
    _log(f"selected item → {repr(results[0]['title'])} (${results[0]['price']})")

    # Step 5: Price comparison (stretch feature — Tool 4)
    session["price_verdict"] = price_comparison(session["selected_item"])

    # Step 6: Suggest outfit
    outfit = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )
    session["outfit_suggestion"] = outfit

    # Step 7: Create fit card
    fit_card = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )
    session["fit_card"] = fit_card

    _log("run_agent → completed successfully")
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("\n\033[1m=== Happy path: graphic tee ===\033[0m\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"\nFound: {session['selected_item']['title']}")
        if session["search_relaxed_note"]:
            print(f"⚠️  {session['search_relaxed_note']}")
        print(f"\nPrice verdict:\n{session['price_verdict']}")
        print(f"\nOutfit:\n{session['outfit_suggestion']}")
        print(f"\nFit card:\n{session['fit_card']}")

    print("\n\n\033[1m=== Fallback retry path: impossible constraints ===\033[0m\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    if session2["error"]:
        print(f"Error: {session2['error']}")
    elif session2["search_relaxed_note"]:
        print(f"⚠️  {session2['search_relaxed_note']}")
        print(f"Found: {session2['selected_item']['title']}")