"""
main.py — CLI entry point for testing without the API server.

Usage:
    python main.py "What is agentic AI?"
    python main.py "Explain transformers" --pdf paper.pdf

Setup:
    1. Copy .env.example to .env
    2. Add your Groq key: GROQ_API_KEY=gsk_...
    3. pip install -r requirements.txt
    4. python main.py "your question"
"""

import sys
import os
import uuid
from pathlib import Path

# ── Load .env BEFORE importing anything that reads settings ───────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

# Validate key is present before running
groq_key = os.getenv("GROQ_API_KEY", "")
if not groq_key or groq_key == "your_groq_key_here":
    print("\n ERROR: GROQ_API_KEY not set.")
    print(" 1. Copy .env.example → .env")
    print(" 2. Set GROQ_API_KEY=gsk_... (get free key at console.groq.com)")
    sys.exit(1)

from loguru import logger
from state import initial_state
from graph import get_graph


def run(query: str, pdf_paths: list[str] | None = None):
    logger.info(f"Starting research: {query}")

    state = initial_state(
        user_query=query,
        session_id=str(uuid.uuid4()),
        pdf_paths=pdf_paths,
    )

    graph = get_graph()
    final_state = graph.invoke(state)

    print("\n" + "="*60)
    print("RESEARCH COMPLETE")
    print("="*60)
    print(f"\nQuery: {query}\n")

    print("Steps taken:")
    for step in final_state.get("steps", []):
        icon = {"orchestrator": "🧠", "web_search": "🔍",
                "pdf_reader": "📄", "code_executor": "💻",
                "summarizer": "✍️"}.get(step.agent.value, "•")
        print(f"  {icon} [{step.agent.value}] {step.action}")

    sources = final_state.get("all_sources", [])
    print(f"\nSources found: {len(sources)}")
    for i, src in enumerate(sources[:5], 1):
        print(f"  [{i}] {src.title[:60]} — {src.url or 'PDF'}")

    print("\n--- FINAL ANSWER ---\n")
    print(final_state.get("final_answer", "No answer generated."))
    print("="*60)

    return final_state


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python main.py "your research question"')
        print('       python main.py "your question" --pdf path/to/file.pdf')
        sys.exit(1)

    query = sys.argv[1]
    pdfs = []
    if "--pdf" in sys.argv:
        idx = sys.argv.index("--pdf")
        if idx + 1 < len(sys.argv):
            pdfs.append(sys.argv[idx + 1])

    run(query, pdfs)
