from __future__ import annotations

import json

from ..models import SessionManifest
from ..prompts import PromptLibrary, render_prompt
from .step2_trend_scenarios import resolve_selected_scenario


def prepare_step3_prompt(
    manifest: SessionManifest,
    prompts: PromptLibrary,
    step1_parsed: dict,
    step2_parsed: dict,
) -> tuple[str, dict]:
    event_payload = {}
    for candidate in step1_parsed.get("candidates", []):
        if candidate.get("id") == manifest.chosen_event:
            event_payload = candidate
            break

    scenario_name = manifest.chosen_scenario or "base"
    scenario_text = resolve_selected_scenario(step2_parsed, scenario_name)

    prompt = render_prompt(
        prompts.step3(),
        target_date=manifest.target_date,
        outlet_name=manifest.chosen_outlet or "не задано",
        event_payload=json.dumps(event_payload, ensure_ascii=False, indent=2),
        scenario_payload=scenario_text or "Сценарий не выбран",
    )

    input_payload = {
        "event": event_payload,
        "scenario_name": scenario_name,
        "scenario_text": scenario_text,
        "outlet": manifest.chosen_outlet,
    }
    return prompt, input_payload
