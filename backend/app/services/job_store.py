import os
import json
import time
import sqlite3
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data"))
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "omnibrain.db")


class JobStore:
    """
    Persistent SQLite storage for:
    1. Background PDF ingestion job states (survives server restarts).
    2. Session-keyed conversation chat history for frontend browser refresh hydration.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_db(self):
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    job_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    error_detail TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    details_json TEXT,
                    created_at REAL NOT NULL
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history (session_id);")
            conn.commit()

    # --- Ingestion Job Operations ---

    def create_job(
        self,
        job_id: str,
        filename: str,
        file_path: str,
        status: str = "QUEUED",
        message: str = "Ingestion job queued automatically after upload."
    ) -> Dict[str, Any]:
        now = time.time()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO ingestion_jobs
                (job_id, filename, file_path, status, message, created_at, updated_at, error_detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, filename, file_path, status, message, now, now, None)
            )
            conn.commit()
        return self.get_job(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        message: Optional[str] = None,
        error_detail: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._connection() as conn:
            cursor = conn.cursor()
            updates = ["updated_at = ?"]
            params = [now]

            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if message is not None:
                updates.append("message = ?")
                params.append(message)
            if error_detail is not None:
                updates.append("error_detail = ?")
                params.append(error_detail)

            params.append(job_id)
            cursor.execute(
                f"UPDATE ingestion_jobs SET {', '.join(updates)} WHERE job_id = ?",
                params
            )
            conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    # --- Chat History Operations ---

    def save_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        now = time.time()
        details_str = None
        if details:
            def _default_serializer(obj):
                if hasattr(obj, "model_dump"):
                    return obj.model_dump()
                if hasattr(obj, "dict"):
                    return obj.dict()
                return str(obj)

            try:
                details_str = json.dumps(details, default=_default_serializer)
            except Exception:
                details_str = None
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chat_history (session_id, role, content, details_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, details_str, now)
            )
            conn.commit()

    def get_chat_history(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content, details_json, created_at FROM chat_history WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            rows = cursor.fetchall()
            messages = []
            for r in rows:
                msg = {
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": r["created_at"]
                }
                if r["details_json"]:
                    try:
                        details = json.loads(r["details_json"])
                        msg.update(details)
                    except Exception:
                        pass
                messages.append(msg)
            return messages

    def clear_chat_history(self, session_id: str) -> None:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
            conn.commit()


# Shared singleton instance
job_store = JobStore()
