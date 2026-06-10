"""
tools.py

The FitFindr tools: search_listings, suggest_outfit, create_fit_card,
and price_comparison (stretch feature).
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# ── simple logger ─────────────────────────────────────────────────────────────

def _log(msg: str):
    """Print a formatted tool-call log line to terminal."""
    print(f"\033[36m[TOOL]\033[0m {msg}")


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Add it to a .env file in the project root.")
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Returns a list of matching listing dicts sorted by relevance score (best first).
    Returns an empty list if nothing matches — never raises an exception.
    """
    size_label = f"size={size}" if size else "no size filter"
    price_label = f"max_price=${max_price:.0f}" if max_price else "no price filter"
    _log(f"search_listings(description={repr(description)}, {size_label}, {price_label})")

    listings = load_listings()

    # Step 1: Filter by price
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Step 2: Filter by size (case-insensitive substring match)
    if size is not None:
        size_lower = size.lower()
        listings = [
            l for l in listings
            if size_lower in l["size"].lower()
        ]

    # Step 3: Score by keyword overlap with description
    keywords = set(re.findall(r"[a-z]+", description.lower()))

    def score(listing: dict) -> int:
        text = " ".join([
            listing["title"],
            listing["description"],
            listing["category"],
            " ".join(listing["style_tags"]),
            listing.get("brand") or "",
        ]).lower()
        words = set(re.findall(r"[a-z]+", text))
        return len(keywords & words)

    scored = [(score(l), l) for l in listings]
    scored = [(s, l) for s, l in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    results = [l for _, l in scored]
    _log(f"search_listings → {len(results)} result(s) found")
    return results


# ── Tool 1b: search_listings_relaxed ─────────────────────────────────────────

def search_listings_relaxed(
    description: str,
    size: str | None,
    max_price: float | None,
) -> tuple[list[dict], str]:
    """
    Stretch feature: retry logic with fallback.
    Tries progressively looser constraints if the strict search returns nothing.
    Returns (results, note_about_what_was_relaxed).
    """
    _log("search_listings_relaxed → starting fallback retry sequence")

    # Attempt 1: full constraints (already tried by caller, but we try again cleanly)
    results = search_listings(description, size, max_price)
    if results:
        return results, ""

    # Attempt 2: drop size filter
    if size is not None:
        _log(f"search_listings_relaxed → no results, retrying without size={size}")
        results = search_listings(description, None, max_price)
        if results:
            note = f"No results in size {size} — showing results for any size instead."
            return results, note

    # Attempt 3: drop price ceiling
    if max_price is not None:
        _log(f"search_listings_relaxed → no results, retrying without price cap")
        results = search_listings(description, size, None)
        if results:
            note = (
                f"Nothing under ${max_price:.0f}"
                + (f" in size {size}" if size else "")
                + " — showing results at any price instead."
            )
            return results, note

    # Attempt 4: drop both
    if size is not None and max_price is not None:
        _log("search_listings_relaxed → retrying with no filters at all")
        results = search_listings(description, None, None)
        if results:
            note = (
                f"Nothing under ${max_price:.0f} in size {size} — "
                "showing results with no size or price filter."
            )
            return results, note

    _log("search_listings_relaxed → all retries exhausted, returning empty")
    return [], ""


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1-2 complete outfits.
    """
    _log(f"suggest_outfit(item={repr(new_item['title'])}, wardrobe_items={len(wardrobe.get('items', []))})")

    client = _get_groq_client()
    items = wardrobe.get("items", [])

    if not items:
        prompt = f"""You are a personal stylist helping someone style a thrifted piece.

The new item they just found:
- Name: {new_item['title']}
- Description: {new_item['description']}
- Style tags: {', '.join(new_item['style_tags'])}
- Colors: {', '.join(new_item['colors'])}
- Category: {new_item['category']}

They haven't told you what's in their closet yet. Give them 2 concrete outfit ideas — \
describe the types of pieces that would pair well with this item (bottoms, shoes, outerwear, etc.), \
the vibe each look creates, and one specific styling tip. Keep it conversational and specific."""
    else:
        wardrobe_lines = "\n".join(
            f"- {item['name']} ({item['category']}, {', '.join(item['colors'])})"
            + (f" — {item['notes']}" if item.get("notes") else "")
            for item in items
        )
        prompt = f"""You are a personal stylist helping someone build outfits from their existing wardrobe.

The new thrifted item they're considering:
- Name: {new_item['title']}
- Description: {new_item['description']}
- Style tags: {', '.join(new_item['style_tags'])}
- Colors: {', '.join(new_item['colors'])}
- Category: {new_item['category']}

Their current wardrobe:
{wardrobe_lines}

Suggest 1-2 complete outfit combinations using the new item and specific named pieces \
from their wardrobe. For each outfit: name the exact pieces, describe the overall vibe, \
and give one styling tip (tuck, roll, layer, accessorize, etc.). Be specific and conversational."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    result = response.choices[0].message.content.strip()
    _log("suggest_outfit → response received")
    return result if result else "Couldn't generate outfit suggestions — try again."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.
    """
    if not outfit or not outfit.strip():
        _log("create_fit_card → skipped (empty outfit input)")
        return "Error: No outfit suggestion provided — run suggest_outfit first before generating a fit card."

    _log(f"create_fit_card(item={repr(new_item['title'])})")

    client = _get_groq_client()

    prompt = f"""You write captions for thrift fashion posts. Write a 2-4 sentence Instagram/TikTok caption \
for this outfit. It should sound authentic and casual — like something a real person would post, not a product ad. \
Mention the item name, the price, and the platform naturally (once each). Capture the vibe in specific terms. \
Use lowercase, light slang is fine, 1-2 emojis max.

Item found: {new_item['title']} — ${new_item['price']} on {new_item['platform']}
Outfit: {outfit}

Write only the caption. No quotes, no preamble."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
        max_tokens=150,
    )
    result = response.choices[0].message.content.strip()
    _log("create_fit_card → response received")
    return result if result else "Error: LLM returned an empty caption — try again."


# ── Tool 4: price_comparison (stretch feature) ────────────────────────────────

def price_comparison(item: dict) -> str:
    """
    Stretch feature: given a listing, compare its price to comparable items
    in the dataset to estimate whether the price is fair.

    Returns a human-readable verdict string. Never raises.
    """
    _log(f"price_comparison(item={repr(item['title'])}, price=${item['price']})")

    listings = load_listings()

    # Build a set of keywords from this item's category + style_tags
    item_keywords = set(re.findall(r"[a-z]+", (
        item["category"] + " " + " ".join(item["style_tags"])
    ).lower()))

    comparables = []
    for l in listings:
        if l["id"] == item["id"]:
            continue  # skip self
        l_keywords = set(re.findall(r"[a-z]+", (
            l["category"] + " " + " ".join(l["style_tags"])
        ).lower()))
        overlap = len(item_keywords & l_keywords)
        if overlap >= 2:
            comparables.append((overlap, l["price"], l["title"]))

    if not comparables:
        _log("price_comparison → no comparables found")
        return "No comparable listings found to benchmark this price."

    prices = [p for _, p, _ in comparables]
    avg = sum(prices) / len(prices)
    low = min(prices)
    high = max(prices)
    item_price = item["price"]

    if item_price <= avg * 0.80:
        verdict = "great deal 🟢"
        detail = f"${item_price:.2f} is well below the average of ${avg:.2f} for similar items."
    elif item_price <= avg * 1.10:
        verdict = "fair price 🟡"
        detail = f"${item_price:.2f} is close to the average of ${avg:.2f} for similar items."
    else:
        verdict = "on the pricier side 🔴"
        detail = f"${item_price:.2f} is above the average of ${avg:.2f} for similar items."

    _log(f"price_comparison → {verdict} (avg=${avg:.2f}, n={len(comparables)})")
    return (
        f"Price verdict: {verdict}\n"
        f"{detail}\n"
        f"Comparable items ranged from ${low:.2f} to ${high:.2f} "
        f"(based on {len(comparables)} similar listing(s))."
    )