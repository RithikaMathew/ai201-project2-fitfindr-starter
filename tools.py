"""
tools.py

The three required FitFindr tools.
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


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
    # Tokenize description into lowercase words (strip punctuation)
    keywords = set(re.findall(r"[a-z]+", description.lower()))

    def score(listing: dict) -> int:
        # Build a bag of words from all text fields + style_tags
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

    # Step 4: Drop zero-score listings
    scored = [(s, l) for s, l in scored if s > 0]

    # Step 5: Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Returns a non-empty string. If the wardrobe is empty, offers general styling
    advice rather than crashing.
    """
    client = _get_groq_client()
    items = wardrobe.get("items", [])

    if not items:
        # Empty wardrobe path: general styling advice
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
        # Format wardrobe items into a readable list
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

Suggest 1–2 complete outfit combinations using the new item and specific named pieces \
from their wardrobe. For each outfit: name the exact pieces, describe the overall vibe, \
and give one styling tip (tuck, roll, layer, accessorize, etc.). Be specific and conversational."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    result = response.choices[0].message.content.strip()
    return result if result else "Couldn't generate outfit suggestions — try again."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Returns a 2–4 sentence caption. If outfit is empty, returns a descriptive
    error message string — never raises an exception.
    """
    if not outfit or not outfit.strip():
        return "Error: No outfit suggestion provided — run suggest_outfit first before generating a fit card."

    client = _get_groq_client()

    prompt = f"""You write captions for thrift fashion posts. Write a 2–4 sentence Instagram/TikTok caption \
for this outfit. It should sound authentic and casual — like something a real person would post, not a product ad. \
Mention the item name, the price, and the platform naturally (once each). Capture the vibe in specific terms. \
Use lowercase, light slang is fine, 1–2 emojis max.

Item found: {new_item['title']} — ${new_item['price']} on {new_item['platform']}
Outfit: {outfit}

Write only the caption. No quotes, no preamble."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,   # Higher temp = more variation each run
        max_tokens=150,
    )
    result = response.choices[0].message.content.strip()
    return result if result else "Error: LLM returned an empty caption — try again."