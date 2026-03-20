"""SQLite + FTS5 persistence for agent sessions and conversations."""
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Generator


@dataclass
class ConversationEntry:
    session_id: str
    agent_name: str
    phase: str
    role: str  # "user", "assistant", "tool"
    content: str
    block_type: str = "text"  # "text", "tool_use", "tool_result"
    cost: float = 0.0
    timestamp: float = 0.0


class MemoryStore:
    """SQLite-backed persistence for agent sessions."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    total_cost REAL DEFAULT 0.0,
                    total_duration REAL DEFAULT 0.0,
                    current_phase TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    block_type TEXT DEFAULT 'text',
                    cost REAL DEFAULT 0.0,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)

            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
                USING fts5(content, agent_name, phase, content=conversations, content_rowid=id)
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
                    INSERT INTO conversations_fts(rowid, content, agent_name, phase)
                    VALUES (new.id, new.content, new.agent_name, new.phase);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
                    INSERT INTO conversations_fts(conversations_fts, rowid, content, agent_name, phase)
                    VALUES ('delete', old.id, old.content, old.agent_name, old.phase);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
                    INSERT INTO conversations_fts(conversations_fts, rowid, content, agent_name, phase)
                    VALUES ('delete', old.id, old.content, old.agent_name, old.phase);
                    INSERT INTO conversations_fts(rowid, content, agent_name, phase)
                    VALUES (new.id, new.content, new.agent_name, new.phase);
                END
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS cost_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    cost REAL NOT NULL,
                    cumulative_cost REAL NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_agent ON conversations(agent_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_session ON cost_tracking(session_id)")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Session methods
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, task: str) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO sessions (id, task, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, task, now, now),
            )

    def update_session(self, session_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        kwargs["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [session_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE sessions SET {cols} WHERE id = ?", vals)  # noqa: S608

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result.get("metadata") or "{}")
        return result

    def list_sessions(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            r = dict(row)
            r["metadata"] = json.loads(r.get("metadata") or "{}")
            out.append(r)
        return out

    # ------------------------------------------------------------------
    # Conversation methods
    # ------------------------------------------------------------------

    def add_conversation(self, entry: ConversationEntry) -> int:
        if entry.timestamp == 0.0:
            entry.timestamp = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO conversations
                   (session_id, agent_name, phase, role, content, block_type, cost, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.session_id,
                    entry.agent_name,
                    entry.phase,
                    entry.role,
                    entry.content,
                    entry.block_type,
                    entry.cost,
                    entry.timestamp,
                ),
            )
            return cursor.lastrowid or 0

    def get_conversations(
        self,
        session_id: str,
        agent_name: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._connect() as conn:
            if agent_name is not None:
                rows = conn.execute(
                    """SELECT * FROM conversations
                       WHERE session_id = ? AND agent_name = ?
                       ORDER BY timestamp ASC LIMIT ?""",
                    (session_id, agent_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM conversations
                       WHERE session_id = ?
                       ORDER BY timestamp ASC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def search_conversations(
        self,
        query: str,
        session_id: str | None = None,
    ) -> list[dict]:
        with self._connect() as conn:
            if session_id is not None:
                rows = conn.execute(
                    """SELECT c.* FROM conversations c
                       JOIN conversations_fts fts ON c.id = fts.rowid
                       WHERE conversations_fts MATCH ?
                         AND c.session_id = ?
                       ORDER BY rank""",
                    (query, session_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT c.* FROM conversations c
                       JOIN conversations_fts fts ON c.id = fts.rowid
                       WHERE conversations_fts MATCH ?
                       ORDER BY rank""",
                    (query,),
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Cost tracking methods
    # ------------------------------------------------------------------

    def record_cost(
        self,
        session_id: str,
        agent_name: str,
        phase: str,
        cost: float,
        cumulative: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO cost_tracking
                   (session_id, agent_name, phase, cost, cumulative_cost, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, agent_name, phase, cost, cumulative, time.time()),
            )
            conn.execute(
                "UPDATE sessions SET total_cost = ?, updated_at = ? WHERE id = ?",
                (cumulative, time.time(), session_id),
            )

    def get_session_cost(self, session_id: str) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT total_cost FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return float(row["total_cost"]) if row else 0.0

    def get_cost_breakdown(self, session_id: str) -> dict[str, float]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT agent_name, SUM(cost) AS agent_total
                   FROM cost_tracking
                   WHERE session_id = ?
                   GROUP BY agent_name""",
                (session_id,),
            ).fetchall()
        return {row["agent_name"]: float(row["agent_total"]) for row in rows}
