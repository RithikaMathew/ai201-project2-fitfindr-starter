"""
app.py

Gradio interface for FitFindr.
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str, str]:
    """
    Called by Gradio when the user submits a query.
    Returns (listing_text, price_verdict, outfit_suggestion, fit_card).
    """
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", "", ""

    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    session = run_agent(query=user_query.strip(), wardrobe=wardrobe)

    if session["error"]:
        return session["error"], "", "", ""

    item = session["selected_item"]

    # Build listing panel — prepend relaxed-search note if constraints were loosened
    relaxed_note = ""
    if session.get("search_relaxed_note"):
        relaxed_note = f"⚠️  {session['search_relaxed_note']}\n\n"

    listing_text = (
        f"{relaxed_note}"
        f"✅ {item['title']}\n\n"
        f"💰 ${item['price']:.2f}  •  📦 {item['platform'].capitalize()}\n"
        f"📏 Size: {item['size']}  •  Condition: {item['condition'].capitalize()}\n"
        f"🏷️ {', '.join(item['style_tags'])}\n\n"
        f"{item['description']}"
    )

    price_verdict = session.get("price_verdict") or ""

    return listing_text, price_verdict, session["outfit_suggestion"], session["fit_card"]


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",
]


def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            price_output = gr.Textbox(
                label="💲 Price verdict",
                lines=4,
                interactive=False,
            )

        with gr.Row():
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        outputs = [listing_output, price_output, outfit_output, fitcard_output]

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()