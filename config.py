"""
config.py — All settings. Only GROQ_API_KEY is required.
Everything else is free and runs locally.

Get your free Groq key at: https://console.groq.com
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Groq (free tier — only required key) ──────────────────────────────────
    groq_api_key: str = ""

    # llama-3.3-70b: best free model, great at planning and reasoning
    orchestrator_model: str = "llama-3.3-70b-versatile"
    # llama-3.1-8b: ultra fast, free, perfect for summarization
    summarizer_model: str = "llama-3.1-8b-instant"

    # ── Web Search (DuckDuckGo — completely free, no key needed) ──────────────
    max_search_results: int = 5

    # ── Embeddings (sentence-transformers — local, free, no API) ──────────────
    # Downloads ~80MB once, then runs fully offline on CPU
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Vector Store (ChromaDB local — free, persists to disk) ────────────────
    chroma_persist_dir: str = "./chroma_db"
    max_pdf_chunk_size: int = 1000
    chunk_overlap: int = 150

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "DEBUG"
    max_iterations: int = 10   # safety guard on the agent loop


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Expose prompt limit so db.py can read from env too
import os
# db.py reads PROMPT_LIMIT directly from env (default 6)
