from __future__ import annotations

import json

from ..models import SessionManifest
from ..prompts import PromptLibrary, render_prompt


SCENARIO_ALIAS = {
    "base": "base_scenario",
    "cautious": "cautious_scenario",
    "stronger": "stronger_scenario",
}


def _select_event_payload(step1_parsed: dict, event_id: str) -> dict:
    for candidate in step1_parsed.get("candidates", []):
        if candidate.get("id") == event_id:
            return candidate
    return {}


def prepare_step2_prompt(
    manifest: SessionManifest,
    prompts: PromptLibrary,
    step1_parsed: dict,
    user_notes: str = "",
) -> tuple[str, dict]:
    event_payload = _select_event_payload(step1_parsed, manifest.chosen_event)
    event_text = json.dumps(event_payload, ensure_ascii=False, indent=2) if event_payload else "Событие не найдено"
    prompt = render_prompt(
        prompts.step2(),
        target_date=manifest.target_date,
        event_payload=event_text,
        user_notes=user_notes or "нет",
    )
    return prompt, event_payload


def resolve_selected_scenario(parsed_step2: dict, scenario_name: str) -> str:
    key = SCENARIO_ALIAS.get(scenario_name.lower(), scenario_name)
    return str(parsed_step2.get(key, "")).strip()
