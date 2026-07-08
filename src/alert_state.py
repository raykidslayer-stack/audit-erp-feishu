from __future__ import annotations

import json
from pathlib import Path


class AlertState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen = self._load()

    def is_new(self, key: str) -> bool:
        if key in self._seen:
            return False
        self._seen.add(key)
        self._save()
        return True

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return set()
        return set(data if isinstance(data, list) else [])

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(sorted(self._seen), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

