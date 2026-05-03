from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from ave.exceptions import TrailError
from ave.models.trail import TrailEntry
from ave.utils.logging import get_logger

logger = get_logger("trail_writer")


class TrailWriter:
    def __init__(self, session_id: str, output_dir: Path) -> None:
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trail_path = self.output_dir / f"{session_id}_trail.jsonl"
        self._handle = self.trail_path.open("a", encoding="utf-8")
        self._finalized = False

        try:
            os.chmod(self.trail_path, 0o600)
        except OSError:
            logger.debug("Unable to set trail file permissions on this platform.")

    def write(self, entry: TrailEntry) -> None:
        if self._finalized:
            raise TrailError("Trail is finalized; no further writes allowed")
        line = entry.to_jsonl_line()
        self._handle.write(line + "\n")
        self._handle.flush()
        logger.debug("Trail entry written: %s", entry.action_type)

    def finalize(self) -> str:
        if self._finalized:
            raise TrailError("Trail is already finalized")
        self._handle.flush()

        with self.trail_path.open("rb") as handle:
            content = handle.read()
        chain_hash = hashlib.sha256(content).hexdigest()

        metadata = TrailEntry(self.session_id)
        chain_entry = {
            "session_id": self.session_id,
            "entry_id": metadata.entry_id,
            "timestamp": metadata.timestamp,
            "agent_id": "trail_writer",
            "action_type": "CHAIN_HASH",
            "input_hash": "",
            "output_hash": chain_hash,
            "reasoning_summary": "Chain hash finalized",
            "human_decision": None,
            "human_decision_timestamp": None,
            "human_decision_note": None,
            "confidence": 1.0,
            "duration_ms": 0,
            "llm_model_used": None,
            "llm_tokens_used": None,
            "chain_hash": chain_hash,
        }
        self._handle.write(json.dumps(chain_entry, ensure_ascii=False) + "\n")
        self._handle.flush()
        self._handle.close()
        self._finalized = True
        return str(self.trail_path)

    def verify(self, trail_path: Path) -> bool:
        path = Path(trail_path)
        if not path.exists():
            return False

        content = path.read_bytes()
        if not content:
            return False

        lines = content.splitlines(keepends=True)
        chain_index: Optional[int] = None
        chain_hash: Optional[str] = None

        for idx in range(len(lines) - 1, -1, -1):
            line = lines[idx].strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("action_type") == "CHAIN_HASH":
                chain_index = idx
                chain_hash = payload.get("chain_hash")
                break

        if chain_index is None or not chain_hash:
            return False

        prior_content = b"".join(lines[:chain_index])
        calculated = hashlib.sha256(prior_content).hexdigest()
        return calculated == chain_hash
