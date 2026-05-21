"""
db.py — SQLite database for user tracking, usage limits, and query logs.

Tables:
  users       — fingerprint-based user records + prompt quota
  query_logs  — every research query with metadata and status
  agent_logs  — per-agent step logs for detailed debugging

All writes are sync-safe; WAL mode enabled for concurrent reads.
"""

from __future__ import annotations
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from loguru import logger

import os

def _resolve_db_path() -> Path:
    # 1. Explicit DB_PATH env var
    if os.getenv("DB_PATH"):
        return Path(os.environ["DB_PATH"])
    # 2. Railway persistent volume mounted at /data
    data_dir = Path("/data")
    if data_dir.exists() and os.access(data_dir, os.W_OK):
        return data_dir / "research_assistant.db"
    # 3. Local development fallback
    return Path("./research_assistant.db")

DB_PATH      = _resolve_db_path()
PROMPT_LIMIT = int(os.getenv("PROMPT_LIMIT", "6"))
RESET_HOURS  = int(os.getenv("RESET_HOURS", "24"))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist. Call once at startup."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            fingerprint     TEXT UNIQUE NOT NULL,
            ip              TEXT,
            first_seen      TEXT NOT NULL,
            last_seen       TEXT NOT NULL,
            prompt_count    INTEGER DEFAULT 0,
            quota_reset_at  TEXT NOT NULL,
            is_blocked      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS query_logs (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            query           TEXT NOT NULL,
            status          TEXT DEFAULT 'pending',
            sources_found   INTEGER DEFAULT 0,
            answer_length   INTEGER DEFAULT 0,
            duration_ms     INTEGER DEFAULT 0,
            error           TEXT,
            created_at      TEXT NOT NULL,
            completed_at    TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS agent_logs (
            id              TEXT PRIMARY KEY,
            query_id        TEXT NOT NULL,
            agent           TEXT NOT NULL,
            action          TEXT NOT NULL,
            status          TEXT NOT NULL,
            detail          TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY(query_id) REFERENCES query_logs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_users_fp   ON users(fingerprint);
        CREATE INDEX IF NOT EXISTS idx_qlogs_user ON query_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_qlogs_time ON query_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_alogs_qid  ON agent_logs(query_id);
        """)
    logger.info(f"[DB] Initialised at {DB_PATH}")


# ── User helpers ──────────────────────────────────────────────────────────────

def get_or_create_user(fingerprint: str, ip: str = "") -> dict:
    now = utcnow()
    # quota resets after RESET_HOURS
    from datetime import timedelta
    reset_at = (datetime.now(timezone.utc) + timedelta(hours=RESET_HOURS)).isoformat()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()

        if row:
            conn.execute(
                "UPDATE users SET last_seen = ?, ip = ? WHERE fingerprint = ?",
                (now, ip, fingerprint)
            )
            return dict(row)

        user_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO users
               (id, fingerprint, ip, first_seen, last_seen, prompt_count, quota_reset_at)
               VALUES (?, ?, ?, ?, ?, 0, ?)""",
            (user_id, fingerprint, ip, now, now, reset_at)
        )
        return {
            "id": user_id, "fingerprint": fingerprint, "ip": ip,
            "first_seen": now, "last_seen": now,
            "prompt_count": 0, "quota_reset_at": reset_at, "is_blocked": 0,
        }


def check_and_increment_quota(user_id: str) -> tuple[bool, int, int]:
    """
    Returns (allowed, prompts_used, prompts_remaining).
    Resets counter if quota_reset_at has passed.
    Increments counter if allowed.
    """
    now = datetime.now(timezone.utc)
    from datetime import timedelta

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

        if not row:
            return False, 0, 0

        if row["is_blocked"]:
            return False, PROMPT_LIMIT, 0

        # Reset quota if window has passed
        reset_at = datetime.fromisoformat(row["quota_reset_at"])
        if now > reset_at:
            new_reset = (now + timedelta(hours=RESET_HOURS)).isoformat()
            conn.execute(
                "UPDATE users SET prompt_count = 0, quota_reset_at = ? WHERE id = ?",
                (new_reset, user_id)
            )
            count = 0
        else:
            count = row["prompt_count"]

        if count >= PROMPT_LIMIT:
            return False, count, 0

        conn.execute(
            "UPDATE users SET prompt_count = prompt_count + 1 WHERE id = ?",
            (user_id,)
        )
        used = count + 1
        return True, used, PROMPT_LIMIT - used


# ── Query log helpers ─────────────────────────────────────────────────────────

def log_query_start(user_id: str, session_id: str, query: str) -> str:
    query_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO query_logs
               (id, user_id, session_id, query, status, created_at)
               VALUES (?, ?, ?, ?, 'running', ?)""",
            (query_id, user_id, session_id, query, utcnow())
        )
    return query_id


def log_query_complete(query_id: str, sources: int, answer_len: int, duration_ms: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE query_logs SET
               status = 'done', sources_found = ?, answer_length = ?,
               duration_ms = ?, completed_at = ?
               WHERE id = ?""",
            (sources, answer_len, duration_ms, utcnow(), query_id)
        )


def log_query_error(query_id: str, error: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE query_logs SET status = 'error', error = ?, completed_at = ? WHERE id = ?",
            (error, utcnow(), query_id)
        )


def log_agent_step(query_id: str, agent: str, action: str, status: str, detail: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO agent_logs (id, query_id, agent, action, status, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), query_id, agent, action, status, detail, utcnow())
        )


# ── Admin query helpers ───────────────────────────────────────────────────────

def get_all_users(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY last_seen DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_queries(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.*, u.fingerprint, u.ip
               FROM query_logs q JOIN users u ON q.user_id = u.id
               ORDER BY q.created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_query_agent_logs(query_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_logs WHERE query_id = ? ORDER BY created_at",
            (query_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_conn() as conn:
        total_users   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_queries = conn.execute("SELECT COUNT(*) FROM query_logs").fetchone()[0]
        done_queries  = conn.execute("SELECT COUNT(*) FROM query_logs WHERE status='done'").fetchone()[0]
        error_queries = conn.execute("SELECT COUNT(*) FROM query_logs WHERE status='error'").fetchone()[0]
        avg_duration  = conn.execute(
            "SELECT AVG(duration_ms) FROM query_logs WHERE status='done'"
        ).fetchone()[0] or 0
        today = datetime.now(timezone.utc).date().isoformat()
        queries_today = conn.execute(
            "SELECT COUNT(*) FROM query_logs WHERE created_at LIKE ?", (f"{today}%",)
        ).fetchone()[0]
    return {
        "total_users":    total_users,
        "total_queries":  total_queries,
        "done_queries":   done_queries,
        "error_queries":  error_queries,
        "avg_duration_ms": round(avg_duration),
        "queries_today":  queries_today,
    }
