from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from ave.context import PipelineContext
from ave.exceptions import StorageError

_LAYER_PATTERN = re.compile(r"layer_(\d+)\.json$")


class CheckpointManager:
    def __init__(self, session_id: str, output_dir: Path) -> None:
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.checkpoint_dir = self.output_dir / ".checkpoints" / session_id
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.checkpoint_dir, 0o700)
        except OSError:
            pass

    def save_checkpoint(self, layer: int, context: PipelineContext) -> None:
        payload = context.to_checkpoint_dict()
        target_path = self.checkpoint_dir / f"layer_{layer}.json"
        manifest_path = self.checkpoint_dir / "manifest.json"

        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=self.checkpoint_dir, encoding="utf-8"
            ) as tmp:
                json.dump(payload, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_name = tmp.name
            os.replace(temp_name, target_path)
        except OSError as exc:
            raise StorageError("Failed to write checkpoint") from exc

        layers = sorted(self._list_layers())
        if layer not in layers:
            layers.append(layer)
        try:
            manifest = {"layers": layers}
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=self.checkpoint_dir, encoding="utf-8"
            ) as tmp:
                json.dump(manifest, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_name = tmp.name
            os.replace(temp_name, manifest_path)
        except OSError as exc:
            raise StorageError("Failed to write checkpoint manifest") from exc

    def load_checkpoint(self, session_id: str, output_dir: Path) -> Optional[dict]:
        checkpoint_dir = Path(output_dir) / ".checkpoints" / session_id
        if not checkpoint_dir.exists():
            return None

        layers = sorted(self._list_layers(checkpoint_dir))
        if not layers:
            return None

        latest = layers[-1]
        target_path = checkpoint_dir / f"layer_{latest}.json"
        try:
            return json.loads(target_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise StorageError("Failed to read checkpoint") from exc

    def has_checkpoint(self, session_id: str, output_dir: Path) -> bool:
        checkpoint_dir = Path(output_dir) / ".checkpoints" / session_id
        if not checkpoint_dir.exists():
            return False
        return bool(self._list_layers(checkpoint_dir))

    def clear_checkpoint(self, session_id: str, output_dir: Path) -> None:
        checkpoint_dir = Path(output_dir) / ".checkpoints" / session_id
        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)

    def _list_layers(self, base_dir: Optional[Path] = None):
        directory = base_dir or self.checkpoint_dir
        layers = []
        for path in directory.glob("layer_*.json"):
            match = _LAYER_PATTERN.match(path.name)
            if match:
                layers.append(int(match.group(1)))
        return layers
