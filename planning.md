# FitFindr — planning.md

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items matching a text description,
with optional filters for size and price. Returns a ranked list of matching
listing dicts, best match first, or an empty list if nothing matches.

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g. "vintage graphic tee"). Used to score relevance via keyword overlap against each listing's title, description, category, style_tags, and brand.
- `size` (str | None): Size string to filter by, case-insensitive substring match (e.g. "M" matches "S/M", "XL (oversized)"). Pass None to skip size filtering.
- `max_price` (float | None): Maximum price (inclusive). Pass None to skip price filtering.

**What it returns:**
A `list[dict]`, each dict being a full listing record with fields:
`id`, `title`, `description`, `category`, `style_tags` (list), `size`,
`condition`, `price` (float), `colors` (list), `brand`, `platform`.
Sorted by keyword overlap score descending. Returns `[]` if no matches — never raises.

**What happens if it fails or returns nothing:**
Returns an empty list. The agent detects `len(results) == 0`, builds a user-friendly
error message that names the specific query parameters that yielded nothing, and returns
early without calling the next two tools.

---

### Tool 2: suggest_outfit

**What it does:**
Given a specific listing and the user's wardrobe, calls the LLM to suggest 1–2
complete outfit combinations. If the wardrobe is empty, gives general styling advice
instead of crashing.

**Input parameters:**
- `new_item` (dict): A listing dict — the item the user is considering. Must have at least `title`, `description`, `style_tags`, `colors`, `category`.
- `wardrobe` (dict): A wardrobe dict with an `'items'` key containing a list of wardrobe item dicts. The list may be empty.

**What it returns:**
A non-empty string. If the wardrobe has items, suggests specific outfit combos
using named wardrobe pieces. If the wardrobe is empty, gives general styling
advice (what types of pieces pair well, what vibe it suits, one styling tip).

**What happens if it fails or returns nothing:**
If the LLM response is empty, returns `"Couldn't generate outfit suggestions — try again."` so the agent can still proceed to create_fit_card.

---

### Tool 3: create_fit_card

**What it does:**
Calls the LLM to generate a short, casual 2–4 sentence Instagram/TikTok-style
caption for the thrifted item and outfit, using high temperature for variation.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from suggest_outfit(). If empty/whitespace, returns an error string immediately without calling the LLM.
- `new_item` (dict): The listing dict for the item found. Used to pull `title`, `price`, and `platform` into the caption naturally.

**What it returns:**
A 2–4 sentence string written in casual lowercase with at most 2 emojis.
Mentions the item name, price, and platform once each. If outfit is empty,
returns a descriptive error message string instead.

**What happens if it fails or returns nothing:**
Guards against empty outfit input before calling the LLM and returns an error
string. If the LLM returns empty, returns `"Error: LLM returned an empty caption — try again."`

---

## Planning Loop

After initializing the session, the agent:

1. Calls `_parse_query()` to extract `description`, `size`, and `max_price` from the raw query using regex. Stores in `session["parsed"]`.
2. Calls `search_listings(description, size, max_price)`. Stores in `session["search_results"]`.
3. **Branch on results:**
   - If `results == []`: set `session["error"]` to a message naming the failed constraints, return session early. `suggest_outfit` and `create_fit_card` are **never called**.
   - If `results` is non-empty: set `session["selected_item"] = results[0]` and continue.
4. Calls `suggest_outfit(selected_item, wardrobe)`. Stores in `session["outfit_suggestion"]`.
5. Calls `create_fit_card(outfit_suggestion, selected_item)`. Stores in `session["fit_card"]`.
6. Returns the completed session.

The agent does **not** call all three tools unconditionally. The only branch point
is after `search_listings` — if it returns nothing, the loop terminates without
ever calling the LLM tools.

---

## State Management

All state lives in the session dict created by `_new_session()`. Fields:

| Field | Set when | Used by |
|-------|----------|---------|
| `query` | init | _parse_query |
| `parsed` | after parsing | search_listings call |
| `search_results` | after search_listings | selected_item selection |
| `selected_item` | after picking top result | suggest_outfit, create_fit_card |
| `wardrobe` | init (passed in) | suggest_outfit |
| `outfit_suggestion` | after suggest_outfit | create_fit_card |
| `fit_card` | after create_fit_card | returned to app.py |
| `error` | if search returns empty | returned to app.py |

No re-entry. No re-prompting the user. Each tool reads from the session and
writes its output back into the session before the next tool is called.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]` to: *"No listings found for '[description]' [in size X] [under $Y]. Try broadening your search — remove the size filter, raise the price limit, or use different keywords."* Returns early; outfit and fit_card stay None. |
| suggest_outfit | Wardrobe is empty | Calls LLM with a general styling prompt instead — returns advice about what types of pieces pair well, not wardrobe-specific combos. Never crashes or returns empty. |
| create_fit_card | Outfit input is missing or empty string | Returns error string immediately without calling LLM: *"Error: No outfit suggestion provided — run suggest_outfit first before generating a fit card."* |

---

## Architecture

```
User query (natural language)
       |
       v
  _parse_query()
  -> description, size, max_price
       |
       v
  search_listings(description, size, max_price)
       |
       +-- results == []
       |       |
       |       v
       |   session["error"] = "No listings found..."
       |   return session  <---- EARLY EXIT
       |
       +-- results non-empty
               |
               v
       session["selected_item"] = results[0]
               |
               v
       suggest_outfit(selected_item, wardrobe)
               |
               +-- wardrobe empty -> general styling advice (LLM)
               +-- wardrobe has items -> specific outfit combos (LLM)
               |
               v
       session["outfit_suggestion"] = "..."
               |
               v
       create_fit_card(outfit_suggestion, selected_item)
               |
               +-- outfit empty -> return error string immediately
               +-- outfit present -> caption (LLM, temp=1.0)
               |
               v
       session["fit_card"] = "..."
               |
               v
       return session
               |
               v
       app.py: map session -> 3 Gradio output panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`: gave Claude the Tool 1 spec (inputs, return value, failure mode,
field list from listings.json) and asked it to implement the function using `load_listings()`
from the data loader, scoring by keyword overlap. Verified that the generated code filtered
by all three parameters and returned `[]` on no match. Tested with 3 queries (graphic tee,
impossible query, price-only filter) before trusting it.

For `suggest_outfit`: gave Claude the Tool 2 spec plus the wardrobe_schema.json structure.
Asked it to write two prompt branches (empty vs. populated wardrobe). Verified the empty-wardrobe
branch returned general advice, not an exception. Ran it manually with `get_empty_wardrobe()`.

For `create_fit_card`: gave Claude the Tool 3 spec and the style guidelines ("casual, lowercase,
1-2 emojis, mention item/price/platform once"). Verified the empty-outfit guard returned an error
string. Ran it 3x on the same input and confirmed outputs differed (temperature=1.0).

**Milestone 4 — Planning loop and state management:**

Gave Claude the Architecture diagram + Planning Loop section. Asked it to implement `run_agent()`
and `_parse_query()` following the numbered steps and branch logic in the diagram. Verified:
(a) the branch after `search_listings` is explicit, not implicit; (b) `selected_item` is the
exact dict that flows into `suggest_outfit`; (c) the no-results path sets `session["error"]`
and returns before calling any LLM tools.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** `_parse_query()` extracts:
- `description` = "vintage graphic tee baggy jeans chunky sneakers"
- `size` = None (not mentioned)
- `max_price` = 30.0

**Step 2:** `search_listings("vintage graphic tee...", size=None, max_price=30.0)`
returns e.g. 3 listings, top result: `"Faded Band Tee -- $22, Depop, Good condition."`
Agent sets `session["selected_item"]` = that listing dict.

**Step 3:** `suggest_outfit(selected_item, example_wardrobe)` -- wardrobe has 10 items.
LLM sees the band tee details + wardrobe. Returns outfit combos using specific named pieces.

**Step 4:** `create_fit_card(outfit_suggestion, selected_item)` -- LLM writes a casual
caption mentioning the item, price, and platform.

**Final output to user:**
- Panel 1 (listing): title, price, platform, size, condition, style tags, description
- Panel 2 (outfit): the 2-combo styling paragraph from suggest_outfit
- Panel 3 (fit card): the casual caption from create_fit_card

**Error path:** If query were "designer ballgown size XXS under $5", search returns [],
agent sets error message naming the constraints, returns early. Panels 2 and 3 are blank.
Panel 1 shows: "No listings found for 'designer ballgown' in size XXS under $5. Try
broadening your search -- remove the size filter, raise the price limit, or use different keywords."

---

## Stretch Features Implemented

### Stretch 1: Retry Logic with Fallback

**What it does:**
`search_listings_relaxed()` wraps `search_listings()` with a 4-attempt retry
sequence. If the strict query returns nothing, it retries with progressively
looser constraints:

1. Strict: description + size + max_price
2. Drop size filter → retry
3. Drop price cap → retry (with original size if present)
4. Drop both → retry with description only

Each successful retry returns a `relaxed_note` string explaining what was loosened,
which surfaces in the listing panel in the UI as a ⚠️ warning.

**Agent changes:**
`run_agent()` now calls `search_listings_relaxed()` instead of `search_listings()`
directly. The returned note is stored in `session["search_relaxed_note"]` and
passed through to `app.py`.

**UI changes:**
If `search_relaxed_note` is set, it prepends the listing panel text with the
warning so users know their constraints were adjusted.

---

### Stretch 2: Price Comparison Tool (Tool 4)

**What it does:**
`price_comparison(item)` finds comparable listings in the dataset by computing
keyword overlap on category + style_tags (≥2 keywords in common). It then
compares the item's price to the mean of comparable prices and returns a
verdict: "great deal 🟢", "fair price 🟡", or "on the pricier side 🔴".

**Input parameters:**
- `item` (dict): A full listing dict. Must have `id`, `price`, `category`, `style_tags`.

**What it returns:**
A human-readable multi-line string with: verdict label, price vs. average
sentence, and a range + count of comparables. Returns a no-comparables message
if the dataset has nothing similar. Never raises.

**Agent changes:**
Called in `run_agent()` between item selection and `suggest_outfit()`.
Result stored in `session["price_verdict"]`.

**UI changes:**
A new "💲 Price verdict" panel was added to the Gradio layout, sitting between
the listing panel and the outfit panels.

---

## Tool Call Visibility (Terminal Logging)

Both `tools.py` and `agent.py` now emit color-coded terminal logs for every
tool call and key decision:

- `[AGENT]` lines (yellow) — parsing, item selection, flow decisions
- `[TOOL]` lines (cyan) — every tool entry, its parameters, and its result count/status

This makes the multi-step flow visible in the terminal during development:

```
[AGENT] run_agent started — query='vintage graphic tee under $30'
[AGENT] parsed → description='vintage graphic tee', size=None, max_price=30.0
[TOOL]  search_listings(description='vintage graphic tee', no size filter, max_price=$30)
[TOOL]  search_listings → 3 result(s) found
[TOOL]  search_listings_relaxed → (no retry needed)
[AGENT] selected item → 'Faded Band Tee' ($22.0)
[TOOL]  price_comparison(item='Faded Band Tee', price=$22.0)
[TOOL]  price_comparison → great deal 🟢 (avg=$31.50, n=4)
[TOOL]  suggest_outfit(item='Faded Band Tee', wardrobe_items=10)
[TOOL]  suggest_outfit → response received
[TOOL]  create_fit_card(item='Faded Band Tee')
[TOOL]  create_fit_card → response received
[AGENT] run_agent → completed successfully
```