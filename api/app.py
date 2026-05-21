"""
api/app.py — FastAPI application factory.
Works locally (reads .env) and on Railway (reads env vars directly).
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from db import init_db


def create_app() -> FastAPI:
    app = FastAPI(
        title="Multi-Agent Research Assistant",
        description="Agentic AI — Groq + LangGraph + DuckDuckGo",
        version="1.0.0",
    )

    # Allow your frontend domain — update after deploying frontend
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", "*"),   # set this in Railway after frontend deploy
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],              # lock to allowed_origins after frontend is live
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup():
        init_db()

    app.include_router(router, prefix="/api")
    return app


app = create_app()
