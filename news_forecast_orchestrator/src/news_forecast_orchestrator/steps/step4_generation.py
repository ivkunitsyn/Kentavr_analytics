from __future__ import annotations

import json

from ..models import SessionManifest
from ..prompts import PromptLibrary, render_prompt
from .step2_trend_scenarios import resolve_selected_scenario


def _selected_event(step1_parsed: dict, event_id: str) -> dict:
    for candidate in step1_parsed.get("candidates", []):
        if candidate.get("id") == event_id:
            return candidate
    return {}


def prepare_step4_prompts(
    manifest: SessionManifest,
    prompts: PromptLibrary,
    step1_parsed: dict,
    step2_parsed: dict,
    step3_parsed: dict,
) -> tuple[dict[str, str], dict]:
    event_payload = _selected_event(step1_parsed, manifest.chosen_event)
    scenario_name = manifest.chosen_scenario or "base"
    scenario_text = resolve_selected_scenario(step2_parsed, scenario_name)

    style_profile = {
        "headline_logic": step3_parsed.get("headline_logic", ""),
        "lead_logic": step3_parsed.get("lead_logic", ""),
        "do_rules": step3_parsed.get("do_rules", []),
        "dont_rules": step3_parsed.get("dont_rules", []),
        "generation_instruction": step3_parsed.get("generation_instruction", ""),
    }

    base_prompt = render_prompt(
        prompts.step4(),
        target_date=manifest.target_date,
        event_payload=json.dumps(event_payload, ensure_ascii=False, indent=2),
        scenario_payload=scenario_text or "Сценарий не выбран",
        outlet_name=manifest.chosen_outlet or "не задано",
        style_profile=json.dumps(style_profile, ensure_ascii=False, indent=2),
    )

    prompts_by_provider = {
        "openai": base_prompt,
        "deepseek": base_prompt,
        "qwen": base_prompt,
    }
    input_payload = {
        "event": event_payload,
        "scenario_name": scenario_name,
        "scenario_text": scenario_text,
        "outlet": manifest.chosen_outlet,
        "style_profile": style_profile,
    }
    return prompts_by_provider, input_payload
