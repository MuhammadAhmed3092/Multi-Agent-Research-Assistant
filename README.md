# Multi-Agent Research Assistant

Agentic AI research system — Groq + LangGraph + DuckDuckGo.
**100% free to run.** Only requires a free Groq API key.

## Features
- Multi-agent pipeline (orchestrator → web search → PDF reader → summarizer)
- **6-prompt daily quota** per user (fingerprint-based, resets every 24h)
- **Full audit logs** — every query, every agent step, stored in SQLite
- **Admin dashboard** via protected REST endpoints
- SSE streaming — live agent progress in the UI
- PDF upload + semantic search (local embeddings, no API cost)

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — set GROQ_API_KEY and ADMIN_KEY

# 3. Run CLI
python main.py "What is agentic AI?"

# 4. Run API server
python server.py                  # http://localhost:8000

# 5. Run frontend (separate terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## Docker Deployment

```bash
cp .env.example .env   # fill in GROQ_API_KEY and ADMIN_KEY
docker compose up --build
# Backend  → http://localhost:8000
# Frontend → http://localhost:5173
```

## Admin Endpoints

All admin routes require the `x-admin-key` header matching your `ADMIN_KEY` env var.

| Endpoint | Description |
|---|---|
| `GET /api/admin/stats` | Total users, queries, avg duration, errors |
| `GET /api/admin/users` | All users with quota status |
| `GET /api/admin/queries` | Recent queries with status |
| `GET /api/admin/queries/{id}/logs` | Per-agent step logs for a query |

```bash
# Example — check stats
curl http://localhost:8000/api/admin/stats \
  -H "x-admin-key: your-admin-key"

# Example — see all users
curl http://localhost:8000/api/admin/users \
  -H "x-admin-key: your-admin-key"
```

## Usage Limiting

- Each user is fingerprinted by **IP + User-Agent** (no login required)
- Limit: **6 prompts per 24 hours** (configurable via `PROMPT_LIMIT` in `.env`)
- Quota shown live in the UI with a progress bar
- After limit: friendly blocked message with reset time shown
- Quota auto-resets after 24h window

## Project Structure

```
research_assistant/
├── .env.example          ← copy to .env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── config.py             ← all settings
├── state.py              ← LangGraph state schema
├── graph.py              ← node + edge wiring
├── db.py                 ← SQLite: users, query logs, agent logs
├── main.py               ← CLI runner
├── server.py             ← uvicorn entry point
│
├── agents/
│   ├── orchestrator.py   ← plans + routes (llama-3.3-70b)
│   ├── web_search.py     ← DuckDuckGo
│   ├── pdf_reader.py     ← PyMuPDF + sentence-transformers + ChromaDB
│   ├── code_executor.py  ← code gen + RestrictedPython sandbox
│   └── summarizer.py     ← synthesis (llama-3.1-8b)
│
├── api/
│   ├── app.py            ← FastAPI factory + DB init on startup
│   └── routes.py         ← /research (SSE), /upload, /quota, /admin/*
│
└── frontend/
    └── src/App.jsx       ← React UI with quota bar + live agent stream
```

## Free Stack

| Component     | Tool                   | Cost  |
|---------------|------------------------|-------|
| LLM           | Groq Llama 3.3 70b     | Free  |
| Web Search    | DuckDuckGo (ddgs)      | Free  |
| Embeddings    | sentence-transformers  | Free  |
| Vector Store  | ChromaDB local         | Free  |
| Code Sandbox  | RestrictedPython       | Free  |
| Database      | SQLite                 | Free  |
>>>>>>> 36125aa (feat: multi-agent research assistant)
