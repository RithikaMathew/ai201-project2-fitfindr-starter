# FitFindr

A Gradio app that searches secondhand listings and generates outfit suggestions and shareable fit cards using a multi-step agent loop.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Or test the agent directly from the command line:

```bash
python agent.py
```

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # All tool functions (search, outfit, fit card, price)
├── agent.py                   # Planning loop and query parser
├── app.py                     # Gradio interface
├── planning.md                # Design decisions, architecture, stretch feature docs
└── requirements.txt
```

---

## Tool Inventory

### Tool 1: `search_listings`

**Purpose:** Searches the mock listings dataset for items matching a natural language description, with optional size and price filters. Returns results ranked by keyword overlap — no LLM involved.

**Signature:**
```python
search_listings(description: str, size: str | None, max_price: float | None) -> list[dict]
```

**Inputs:**
- `description` (str) — keywords extracted from the user query (e.g. `"vintage graphic tee"`). Scored against each listing's title, description, category, style_tags, and brand via word-level overlap.
- `size` (str | None) — size string for case-insensitive substring filtering (e.g. `"M"` matches `"S/M"`). Pass `None` to skip size filtering.
- `max_price` (float | None) — inclusive price ceiling in dollars. Pass `None` to skip price filtering.

**Output:** `list[dict]` — full listing records sorted by relevance score descending. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns `[]` if nothing matches; never raises.

---

### Tool 1b: `search_listings_relaxed` *(stretch feature)*

**Purpose:** Wraps `search_listings` with a 4-attempt fallback retry sequence. If the strict query returns nothing, it retries with progressively looser constraints.

**Signature:**
```python
search_listings_relaxed(description: str, size: str | None, max_price: float | None) -> tuple[list[dict], str]
```

**Inputs:** Same as `search_listings`.

**Output:** `tuple[list[dict], str]` — the results list (may be empty after all retries) and a plain-English note describing what was relaxed, e.g. `"No results in size XXS — showing results for any size instead."` The note is an empty string if no relaxation was needed.

**Retry sequence:**
1. Strict: description + size + max_price
2. Drop size → retry
3. Drop price cap → retry
4. Drop both → retry

---

### Tool 2: `suggest_outfit`

**Purpose:** Given the selected listing and the user's wardrobe, calls the LLM to suggest 1–2 complete outfit combinations. Handles the empty-wardrobe case without crashing.

**Signature:**
```python
suggest_outfit(new_item: dict, wardrobe: dict) -> str
```

**Inputs:**
- `new_item` (dict) — a listing dict from `search_listings`. Must contain `title`, `description`, `style_tags`, `colors`, `category`.
- `wardrobe` (dict) — a wardrobe dict with an `"items"` key (list of dicts, may be empty). Each item has `name`, `category`, `colors`, and optional `notes`.

**Output:** Non-empty string. If `wardrobe["items"]` is non-empty, names specific pieces from the wardrobe and describes outfit combos. If the wardrobe is empty, returns general styling advice (types of pieces that pair well, vibe, one styling tip). Falls back to `"Couldn't generate outfit suggestions — try again."` if the LLM returns empty.

---

### Tool 3: `create_fit_card`

**Purpose:** Generates a short, casual 2–4 sentence Instagram/TikTok-style caption for the found item and outfit. Uses temperature 1.0 so each run produces a different caption.

**Signature:**
```python
create_fit_card(outfit: str, new_item: dict) -> str
```

**Inputs:**
- `outfit` (str) — the outfit suggestion string from `suggest_outfit`. If empty or whitespace, returns an error string immediately without calling the LLM.
- `new_item` (dict) — the listing dict. Used to pull `title`, `price`, and `platform` into the caption.

**Output:** A 2–4 sentence string in casual lowercase, at most 2 emojis, mentioning item name, price, and platform once each. Returns an error string if `outfit` is empty or the LLM returns nothing.

---

### Tool 4: `price_comparison` *(stretch feature)*

**Purpose:** Estimates whether the selected item's price is fair by comparing it to similar listings in the dataset. Fully local — no LLM.

**Signature:**
```python
price_comparison(item: dict) -> str
```

**Inputs:**
- `item` (dict) — a full listing dict. Uses `id`, `price`, `category`, and `style_tags`.

**Output:** A human-readable multi-line string with a verdict label (`"great deal 🟢"`, `"fair price 🟡"`, or `"on the pricier side 🔴"`), a sentence comparing the item's price to the average of comparables, and the price range and count. Returns `"No comparable listings found..."` if there are fewer than 2 keyword matches with any other listing. Never raises.

**Comparable matching:** Any listing (excluding self) with ≥2 keyword tokens in common across `category + style_tags` is counted as a comparable.

---

## Planning Loop

`run_agent(query, wardrobe)` in `agent.py` runs the following sequence:

1. **Parse query** — `_parse_query()` uses regex to extract `description`, `size`, and `max_price` from the raw natural language input. Size is matched as a standalone token (e.g. `M`, `XL`, `S/M`). Price is matched from patterns like `"under $30"` or `"30 dollars"`. The remaining text, stripped of size/price fragments and filler words, becomes the description.

2. **Search with fallback** — calls `search_listings_relaxed(description, size, max_price)`. This tries the strict query first. If it returns nothing, it retries up to three more times with progressively relaxed constraints (drop size → drop price → drop both). Returns the first non-empty result set plus a note explaining any relaxation.

3. **Branch on results:**
   - If still empty after all retries → set `session["error"]` to a message naming the failed constraints, return session immediately. `price_comparison`, `suggest_outfit`, and `create_fit_card` are never called.
   - If non-empty → set `session["selected_item"] = results[0]` and continue.

4. **Price comparison** — calls `price_comparison(selected_item)` and stores the verdict in `session["price_verdict"]`.

5. **Outfit suggestion** — calls `suggest_outfit(selected_item, wardrobe)` and stores the result in `session["outfit_suggestion"]`.

6. **Fit card** — calls `create_fit_card(outfit_suggestion, selected_item)` and stores the result in `session["fit_card"]`.

7. Return the completed session dict. `app.py` maps each field to a Gradio output panel.

The only branch is after the search step. The LLM tools (steps 4–6) are never reached if search returns nothing. Within `suggest_outfit`, there's a secondary branch: empty vs. populated wardrobe, which changes the prompt but not the control flow.

---

## State Management

All state lives in a single session dict created at the start of `run_agent()`. Nothing is global; the dict is passed between steps within one function call.

| Field | Initialized | Set by | Read by |
|---|---|---|---|
| `query` | `_new_session()` | — | `_parse_query` |
| `parsed` | `_new_session()` (as `{}`) | `_parse_query` | `search_listings_relaxed` call |
| `search_results` | `_new_session()` (as `[]`) | `search_listings_relaxed` | item selection |
| `selected_item` | `_new_session()` (as `None`) | agent (picks `results[0]`) | `price_comparison`, `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `_new_session()` (passed in) | — | `suggest_outfit` |
| `price_verdict` | `_new_session()` (as `None`) | `price_comparison` | `app.py` |
| `outfit_suggestion` | `_new_session()` (as `None`) | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `_new_session()` (as `None`) | `create_fit_card` | `app.py` |
| `search_relaxed_note` | `_new_session()` (as `None`) | `search_listings_relaxed` | `app.py` |
| `error` | `_new_session()` (as `None`) | agent (on empty search) | `app.py` |

Each tool receives what it needs as explicit arguments (not the whole session dict). The agent reads the return value and writes it into the session before calling the next tool. No tool reads directly from the session.

---

## Error Handling

| Tool | Failure mode | Behavior | Concrete example |
|---|---|---|---|
| `search_listings` | No listings pass price + size + keyword filters | Returns `[]` — never raises | `search_listings('designer ballgown', size='XXS', max_price=5)` → `[]` (confirmed in terminal: `[TOOL] search_listings → 0 result(s) found`) |
| `search_listings_relaxed` | Strict search empty, but relaxed search finds results | Returns results + a note string explaining what was loosened | Query `"designer ballgown size XXS under $5"` fails strict search, then succeeds after dropping both size and price filters — note: `"Nothing under $5 in size XXS — showing results with no size or price filter."` |
| `search_listings_relaxed` | All retries exhausted | Returns `([], "")` | Truly novel query with no keyword overlap to any listing |
| `suggest_outfit` | Wardrobe is empty | Switches to a general styling prompt — no crash, no empty return | `suggest_outfit(results[0], get_empty_wardrobe())` returns 2 outfit ideas with general pairing advice instead of wardrobe-specific combos (confirmed in terminal test) |
| `create_fit_card` | `outfit` param is empty string | Returns error string immediately, LLM never called | `create_fit_card('', results[0])` → `"Error: No outfit suggestion provided..."` (confirmed: `[TOOL] create_fit_card → skipped (empty outfit input)`) |
| `create_fit_card` | LLM returns empty string | Returns `"Error: LLM returned an empty caption — try again."` | Not triggered in testing; guard exists for robustness |
| `price_comparison` | No comparable listings found (< 2 keyword matches with any other listing) | Returns a no-comparables message string | Highly specific or unique items with unusual tag combinations |

---

## Spec Reflection

**One way the spec helped:** The explicit branch condition in the planning loop spec — "if `results == []`, return early; LLM tools are never called" — was the single most useful constraint to have written down before coding. It made the early-exit logic unambiguous and prevented the temptation to call `suggest_outfit` with a None item and let it fail downstream.

**One way implementation diverged:** The spec described a single `search_listings` call with a hard early-exit on empty results. In implementation, this was split into `search_listings` (strict, pure) and `search_listings_relaxed` (the retry wrapper), and the agent calls the relaxed version. The reason was that the "designer ballgown under $5" test case produced a hard error with no output at all, which felt like a bad user experience for what was just an overly tight price filter. The strict function still exists as a standalone utility; the relaxed wrapper adds behavior on top of it without changing the underlying logic.

---

## AI Usage

**Instance 1 — `suggest_outfit` prompt branching:**
Directed the AI to implement `suggest_outfit` with two distinct prompt branches: one for an empty wardrobe and one for a populated wardrobe. The AI generated both branches correctly but used generic placeholder text like "their wardrobe includes: {wardrobe_lines}" without formatting the individual items. Revised the wardrobe formatting to include category, colors, and notes inline for each item, so the LLM could actually reference specific pieces by name in its response.

**Instance 2 — `search_listings_relaxed` retry sequence:**
Directed the AI to implement the fallback retry wrapper following a 4-step relaxation sequence (strict → drop size → drop price → drop both). The AI generated the sequence but structured it as nested if/else blocks that were hard to follow and had redundant search calls. Rewrote it as a flat sequence of guarded early returns — each retry attempt checks one condition, returns immediately on success, and falls through otherwise. This made the retry order explicit and easy to audit.

**Instance 3 — `price_comparison` comparable matching threshold:**
The AI initially set the comparables threshold at ≥1 keyword overlap, which caused nearly every listing to be considered comparable to every other (since most share words like "vintage" or "top"). Overrode this to ≥2 keywords, which produced tighter peer groups. Verified by checking which listings were grouped together for a few test items.

