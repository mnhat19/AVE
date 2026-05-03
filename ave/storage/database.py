from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ave.exceptions import StorageError
from ave.models.finding import Finding


class AveDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        def _create(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    input_file_path TEXT NOT NULL,
                    input_file_hash TEXT NOT NULL,
                    config_file_path TEXT,
                    config_hash TEXT,
                    row_count INTEGER,
                    column_count INTEGER,
                    overall_rating TEXT,
                    total_findings INTEGER DEFAULT 0,
                    ave_version TEXT NOT NULL,
                    trail_file_path TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    layer INTEGER NOT NULL,
                    finding_type TEXT NOT NULL,
                    rule_id TEXT,
                    rule_name TEXT,
                    row_index INTEGER NOT NULL,
                    column_name TEXT,
                    actual_value TEXT,
                    expected_value TEXT,
                    severity TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    reasoning TEXT NOT NULL,
                    detection_method TEXT NOT NULL,
                    cross_verified INTEGER NOT NULL DEFAULT 0,
                    cross_verify_status TEXT,
                    human_decision TEXT,
                    human_decision_at TEXT,
                    human_decision_note TEXT,
                    created_at TEXT NOT NULL,
                    row_data TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rule_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    rule_yaml TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    called_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    layer INTEGER NOT NULL,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    duration_ms INTEGER,
                    success INTEGER NOT NULL DEFAULT 1,
                    error_message TEXT
                )
                """
            )

        with self._connect() as conn:
            _create(conn)

    def _run_with_retry(self, operation):
        for attempt in range(3):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() and attempt < 2:
                    time.sleep(0.1)
                    continue
                raise StorageError("SQLite operation failed") from exc

    def create_session(self, session: Dict[str, Any]) -> None:
        def _op():
            columns = ",".join(session.keys())
            placeholders = ",".join(["?"] * len(session))
            values = list(session.values())
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO sessions ({columns}) VALUES ({placeholders})",
                    values,
                )

        self._run_with_retry(_op)

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> None:
        def _op():
            assignments = ",".join([f"{key}=?" for key in updates.keys()])
            values = list(updates.values()) + [session_id]
            with self._connect() as conn:
                cursor = conn.execute(
                    f"UPDATE sessions SET {assignments} WHERE session_id = ?",
                    values,
                )
                if cursor.rowcount == 0:
                    raise StorageError(f"Session not found: {session_id}")

        self._run_with_retry(_op)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        def _op():
            with self._connect() as conn:
                cursor = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

        return self._run_with_retry(_op)

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        def _op():
            with self._connect() as conn:
                cursor = conn.execute(
                    "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]

        return self._run_with_retry(_op)

    def save_finding(self, finding: Finding) -> None:
        data = finding.to_dict()
        data["row_data"] = json.dumps(data.get("row_data", {}), ensure_ascii=False)
        data["cross_verified"] = 1 if data.get("cross_verified") else 0

        def _op():
            columns = ",".join(data.keys())
            placeholders = ",".join(["?"] * len(data))
            values = list(data.values())
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO findings ({columns}) VALUES ({placeholders})",
                    values,
                )

        self._run_with_retry(_op)

    def get_findings(self, session_id: str) -> List[Finding]:
        def _op():
            with self._connect() as conn:
                cursor = conn.execute(
                    "SELECT * FROM findings WHERE session_id = ?",
                    (session_id,),
                )
                findings = []
                for row in cursor.fetchall():
                    data = dict(row)
                    data["row_data"] = json.loads(data.get("row_data") or "{}")
                    data["cross_verified"] = bool(data.get("cross_verified"))
                    findings.append(Finding(**data))
                return findings

        return self._run_with_retry(_op)

    def save_rule_snapshot(self, session_id: str, rules: List[dict]) -> None:
        def _op():
            with self._connect() as conn:
                for rule in rules:
                    conn.execute(
                        """
                        INSERT INTO rule_snapshots
                            (session_id, rule_id, rule_name, rule_yaml, active)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            rule.get("id"),
                            rule.get("name", ""),
                            json.dumps(rule, ensure_ascii=False),
                            1 if rule.get("active", True) else 0,
                        ),
                    )

        self._run_with_retry(_op)

    def save_llm_call(self, call_data: Dict[str, Any]) -> None:
        def _op():
            columns = ",".join(call_data.keys())
            placeholders = ",".join(["?"] * len(call_data))
            values = list(call_data.values())
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO llm_calls ({columns}) VALUES ({placeholders})",
                    values,
                )

        self._run_with_retry(_op)

    def get_llm_stats(self, session_id: str) -> Dict[str, Any]:
        def _op():
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total_calls,
                        SUM(prompt_tokens) AS prompt_tokens,
                        SUM(completion_tokens) AS completion_tokens,
                        SUM(duration_ms) AS total_duration_ms,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS success_calls
                    FROM llm_calls
                    WHERE session_id = ?
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else {}

        return self._run_with_retry(_op)
