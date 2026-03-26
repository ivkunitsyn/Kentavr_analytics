from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from .models import SessionManifest
from .storage import SessionStorage


class SessionService:
    def __init__(self, storage: SessionStorage) -> None:
        self.storage = storage

    def create_session(
        self,
        target_date: str,
        country: str = "Россия",
        topic: str = "",
        chosen_outlet: str = "",
    ) -> SessionManifest:
        session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.storage.ensure_session_layout(session_id)
        manifest = SessionManifest(
            session_id=session_id,
            target_date=target_date,
            country=country,
            topic=topic,
            chosen_outlet=chosen_outlet,
            current_step="created",
        )
        self.save_manifest(manifest)
        return manifest

    def load_manifest(self, session_id: str) -> SessionManifest:
        payload = self.storage.read_json(session_id, "manifest.json")
        return SessionManifest(**payload)

    def save_manifest(self, manifest: SessionManifest) -> None:
        self.storage.write_json(manifest.session_id, "manifest.json", asdict(manifest))

    def register_file(self, manifest: SessionManifest, relative_path: str) -> None:
        if relative_path not in manifest.files:
            manifest.files.append(relative_path)

    def update_step(self, manifest: SessionManifest, step_name: str) -> None:
        manifest.current_step = step_name

    def set_chosen_event(self, manifest: SessionManifest, event_id: str) -> None:
        manifest.chosen_event = event_id

    def set_chosen_scenario(self, manifest: SessionManifest, scenario_name: str) -> None:
        manifest.chosen_scenario = scenario_name

    def set_chosen_outlet(self, manifest: SessionManifest, outlet_name: str) -> None:
        manifest.chosen_outlet = outlet_name
