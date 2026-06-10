"""
agent.py

The FitFindr planning loop.
"""

import re
import os

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


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
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.

    Uses regex heuristics — no LLM call needed for this simple extraction.
    Falls back gracefully if size or price aren't mentioned.
    """
    # Extract max price: "under $30", "$30", "30 dollars", "under 30"
    price_match = re.search(
        r"(?:under|less than|max|up to)?\s*\$?\s*(\d+(?:\.\d+)?)\s*(?:dollars?)?",
        query,
        re.IGNORECASE,
    )
    max_price = float(price_match.group(1)) if price_match else None

    # Extract size: standalone S/M/L/XL/XXL/XS or "size M" etc.
    size_match = re.search(
        r"\b(?:size\s+)?([xX]{0,2}[sSlLmM](?:/[sSlLmM])?|[xX][sSlL]|XXL|XL|XS)\b",
        query,
    )
    size = size_match.group(1).upper() if size_match else None

    # Description: remove price and size fragments, strip leftover filler
    description = query
    if price_match:
        description = description[:price_match.start()] + description[price_match.end():]
    if size_match:
        description = description[:size_match.start()] + description[size_match.end():]
    # Clean up common filler phrases
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

    Planning loop logic:
      1. Parse query → description, size, max_price
      2. search_listings() → if empty, set error and return early
      3. select top result → suggest_outfit()
      4. create_fit_card() → done
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: Search listings
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    # Early exit if no results
    if not results:
        size_note = f" in size {parsed['size']}" if parsed["size"] else ""
        price_note = f" under ${parsed['max_price']:.0f}" if parsed["max_price"] else ""
        session["error"] = (
            f"No listings found for \"{parsed['description']}\"{size_note}{price_note}. "
            "Try broadening your search — remove the size filter, raise the price limit, "
            "or use different keywords."
        )
        return session

    # Step 4: Select top result
    session["selected_item"] = results[0]

    # Step 5: Suggest outfit
    outfit = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )
    session["outfit_suggestion"] = outfit

    # Step 6: Create fit card
    fit_card = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )
    session["fit_card"] = fit_card

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")