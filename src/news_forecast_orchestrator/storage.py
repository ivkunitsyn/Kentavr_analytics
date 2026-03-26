from __future__ import annotations

import json
from pathlib import Path


class SessionStorage:
    STEP_DIRS = ("step1", "step2", "step3", "step4", "exports")

    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def ensure_session_layout(self, session_id: str) -> Path:
        root = self.session_dir(session_id)
        root.mkdir(parents=True, exist_ok=True)
        for step_name in self.STEP_DIRS:
            (root / step_name).mkdir(parents=True, exist_ok=True)
        return root

    def step_dir(self, session_id: str, step_name: str) -> Path:
        path = self.session_dir(session_id) / step_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_text(self, session_id: str, relative_path: str, content: str) -> Path:
        target = self.session_dir(session_id) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_text(self, session_id: str, relative_path: str) -> str:
        target = self.session_dir(session_id) / relative_path
        return target.read_text(encoding="utf-8")

    def write_json(self, session_id: str, relative_path: str, payload: dict | list) -> Path:
        target = self.session_dir(session_id) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def read_json(self, session_id: str, relative_path: str) -> dict:
        target = self.session_dir(session_id) / relative_path
        return json.loads(target.read_text(encoding="utf-8"))

    def exists(self, session_id: str, relative_path: str) -> bool:
        return (self.session_dir(session_id) / relative_path).exists()
