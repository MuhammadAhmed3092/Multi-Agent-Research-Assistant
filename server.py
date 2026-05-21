"""
server.py — Start the FastAPI server.

Run locally:    python server.py
Run with Docker: docker compose up --build
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env FIRST before anything reads settings
load_dotenv(Path(__file__).parent / ".env", override=True)

# Validate required keys
groq_key   = os.getenv("GROQ_API_KEY", "")
admin_key  = os.getenv("ADMIN_KEY", "")

if not groq_key or groq_key.startswith("gsk_your"):
    print("\n  ERROR: GROQ_API_KEY not set in .env")
    print("  Get your free key at https://console.groq.com\n")
    exit(1)

if not admin_key or admin_key == "change-this-to-a-strong-secret":
    print("\n  ERROR: ADMIN_KEY not set in .env")
    print("  Generate one: python -c \"import secrets; print(secrets.token_hex(32))\"\n")
    exit(1)

import uvicorn

if __name__ == "__main__":
    env = os.getenv("APP_ENV", "development")
    print(f"\n  Starting Research Assistant API ({env})")
    print(f"  API:  http://localhost:8000")
    print(f"  Docs: http://localhost:8000/docs\n")

    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=(env == "development"),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
