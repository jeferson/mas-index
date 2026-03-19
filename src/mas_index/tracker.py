import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Tracker:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                converted_at TEXT,
                indexed_at TEXT
            )
        """)
        self._conn.commit()

    def needs_processing(self, file_path: str, file_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT file_hash, status FROM files WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if row is None:
            return True
        return row["file_hash"] != file_hash or row["status"] == "failed"

    def set_pending(self, file_path: str, file_hash: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO files (file_path, file_hash, status) VALUES (?, ?, 'pending')",
            (file_path, file_hash),
        )
        self._conn.commit()

    def set_converted(self, file_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE files SET status = 'converted', converted_at = ? WHERE file_path = ?",
            (now, file_path),
        )
        self._conn.commit()

    def set_indexed(self, file_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE files SET status = 'indexed', indexed_at = ? WHERE file_path = ?",
            (now, file_path),
        )
        self._conn.commit()

    def set_failed(self, file_path: str, error: str) -> None:
        self._conn.execute(
            "UPDATE files SET status = 'failed', error_message = ? WHERE file_path = ?",
            (error, file_path),
        )
        self._conn.commit()

    def get_status_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM files GROUP BY status"
        ).fetchall()
        return {row["status"]: row["cnt"] for row in rows}

    def get_failed(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT file_path, error_message FROM files WHERE status = 'failed'"
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._conn.close()
