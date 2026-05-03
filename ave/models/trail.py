from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


@dataclass
class TrailEntry:
    session_id: str
    entry_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    agent_id: str = ""
    action_type: str = ""
    input_hash: str = ""
    output_hash: str = ""
    reasoning_summary: str = ""
    human_decision: Optional[str] = None
    human_decision_timestamp: Optional[str] = None
    human_decision_note: Optional[str] = None
    confidence: float = 1.0
    duration_ms: int = 0
    llm_model_used: Optional[str] = None
    llm_tokens_used: Optional[int] = None

    def __post_init__(self) -> None:
        if len(self.reasoning_summary) > 500:
            raise ValueError("reasoning_summary must be <= 500 characters")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")

    def to_jsonl_line(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_jsonl_line(cls, line: str) -> "TrailEntry":
        data = json.loads(line)
        return cls(**data)
