from __future__ import annotations

import json
import re
from typing import Any


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_labeled(block: str, labels: dict[str, str]) -> dict[str, str]:
    result = {target_key: "" for target_key in labels.values()}
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    for line in lines:
        for label, target_key in labels.items():
            if line.lower().startswith(label.lower()):
                value = line.split(":", 1)[1].strip() if ":" in line else ""
                result[target_key] = value
    return result


def _maybe_json(raw_text: str) -> Any | None:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


def parse_step1(raw_text: str) -> dict:
    payload = _maybe_json(raw_text)
    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        return payload

    lines = _clean_lines(raw_text)
    candidates: list[dict[str, str]] = []
    best_for_outlets = {"РБК": [], "Коммерсантъ": [], "Ведомости": []}

    current_section = "candidates"
    current_item: dict[str, str] | None = None

    for line in lines:
        upper_line = line.upper()
        if "ПОТЕНЦИАЛЬНО ЛУЧШИЕ ДЛЯ РБК" in upper_line:
            current_section = "rbk"
            current_item = None
            continue
        if "ПОТЕНЦИАЛЬНО ЛУЧШИЕ ДЛЯ КОММЕРСАН" in upper_line:
            current_section = "komm"
            current_item = None
            continue
        if "ПОТЕНЦИАЛЬНО ЛУЧШИЕ ДЛЯ ВЕДОМОСТ" in upper_line:
            current_section = "ved"
            current_item = None
            continue

        match = re.match(r"^(\d+)[\.)]\s*(.+)$", line)
        if current_section == "candidates" and match:
            if current_item:
                candidates.append(current_item)
            idx, title = match.groups()
            current_item = {
                "id": f"event_{int(idx):02d}",
                "title": title.strip(),
                "description": "",
                "why_relevant": "",
                "confidence": "средний",
                "outlet_fit": "",
                "source_notes": "",
            }
            continue

        if current_section in {"rbk", "komm", "ved"} and match:
            _, title = match.groups()
            outlet_key = {
                "rbk": "РБК",
                "komm": "Коммерсантъ",
                "ved": "Ведомости",
            }[current_section]
            best_for_outlets[outlet_key].append(title.strip())
            continue

        if current_section == "candidates" and current_item is not None:
            if line.lower().startswith("что это"):
                current_item["description"] = line.split(":", 1)[1].strip() if ":" in line else ""
            elif line.lower().startswith("почему"):
                current_item["why_relevant"] = line.split(":", 1)[1].strip() if ":" in line else ""
            elif line.lower().startswith("лучшее сми"):
                current_item["outlet_fit"] = line.split(":", 1)[1].strip() if ":" in line else ""
            elif line.lower().startswith("уровень уверенности"):
                current_item["confidence"] = line.split(":", 1)[1].strip() if ":" in line else "средний"
            elif line.lower().startswith("источник"):
                current_item["source_notes"] = line.split(":", 1)[1].strip() if ":" in line else ""
            elif line.lower().startswith("главный риск"):
                risk = line.split(":", 1)[1].strip() if ":" in line else ""
                current_item["source_notes"] = f"{current_item['source_notes']} | Риск: {risk}".strip(" |")

    if current_item:
        candidates.append(current_item)

    if not candidates and lines:
        candidates = [
            {
                "id": "event_01",
                "title": lines[0][:120],
                "description": "Автораспознавание не нашло структурированные блоки, сохранён сырой текст.",
                "why_relevant": "",
                "confidence": "средний",
                "outlet_fit": "",
                "source_notes": "",
            }
        ]

    return {
        "candidates": candidates,
        "best_for_outlets": best_for_outlets,
        "raw_text_fallback": True,
    }


def _extract_section(text: str, start_pattern: str, end_patterns: list[str]) -> str:
    start = re.search(start_pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not start:
        return ""
    start_idx = start.end()
    end_idx = len(text)
    for pattern in end_patterns:
        m = re.search(pattern, text[start_idx:], flags=re.IGNORECASE | re.MULTILINE)
        if m:
            end_idx = min(end_idx, start_idx + m.start())
    return text[start_idx:end_idx].strip()


def parse_step2(raw_text: str, event_id: str = "") -> dict:
    payload = _maybe_json(raw_text)
    if isinstance(payload, dict) and {"base_scenario", "cautious_scenario", "stronger_scenario"}.issubset(payload.keys()):
        return payload

    current_context = _extract_section(
        raw_text,
        r"1\.\s*ТЕКУЩАЯ\s+ПОВЕСТКА",
        [r"2\.\s*КЛЮЧЕВЫЕ\s+ТРЕНДЫ", r"3\.\s*СЦЕНАРИИ"],
    )

    trends_block = _extract_section(
        raw_text,
        r"2\.\s*КЛЮЧЕВЫЕ\s+ТРЕНДЫ",
        [r"3\.\s*СЦЕНАРИИ", r"БАЗОВЫЙ\s+СЦЕНАРИЙ"],
    )
    trends = []
    for line in _clean_lines(trends_block):
        m = re.match(r"^\d+[\.)]\s*(.+)$", line)
        if m:
            trends.append(m.group(1).strip())

    base = _extract_section(
        raw_text,
        r"БАЗОВЫЙ\s+СЦЕНАРИЙ",
        [r"ОСТОРОЖНЫЙ\s+СЦЕНАРИЙ", r"БОЛЕЕ\s+СИЛЬНЫЙ\s+СЦЕНАРИЙ", r"4\.\s*ИТОГОВЫЙ"],
    )
    cautious = _extract_section(
        raw_text,
        r"ОСТОРОЖНЫЙ\s+СЦЕНАРИЙ",
        [r"БОЛЕЕ\s+СИЛЬНЫЙ\s+СЦЕНАРИЙ", r"4\.\s*ИТОГОВЫЙ"],
    )
    stronger = _extract_section(
        raw_text,
        r"БОЛЕЕ\s+СИЛЬНЫЙ\s+СЦЕНАРИЙ",
        [r"4\.\s*ИТОГОВЫЙ"],
    )

    selected = ""
    for line in _clean_lines(raw_text):
        if "наиболее пригодный сценарий" in line.lower() and ":" in line:
            selected = line.split(":", 1)[1].strip()
            break

    return {
        "event_id": event_id,
        "current_context": current_context,
        "trends": trends,
        "base_scenario": base,
        "cautious_scenario": cautious,
        "stronger_scenario": stronger,
        "selected_scenario": selected,
        "raw_text_fallback": True,
    }


def _extract_rules(text: str) -> list[str]:
    rules: list[str] = []
    for line in _clean_lines(text):
        if re.match(r"^(\d+[\.)]|[-—])", line):
            rule = re.sub(r"^(\d+[\.)]|[-—])\s*", "", line).strip()
            if rule:
                rules.append(rule)
    return rules


def parse_step3(raw_text: str, outlet_name: str = "") -> dict:
    payload = _maybe_json(raw_text)
    if isinstance(payload, dict) and payload.get("outlet_name"):
        return payload

    headline_logic = _extract_section(
        raw_text,
        r"3\.\s*КАК\s+УСТРОЕН\s+ЗАГОЛОВОК",
        [r"4\.\s*КАК\s+УСТРОЕН\s+ПЕРВЫЙ", r"5\.\s*ЛЕКСИЧЕСКИЕ"],
    )
    lead_logic = _extract_section(
        raw_text,
        r"4\.\s*КАК\s+УСТРОЕН\s+ПЕРВЫЙ\s+АБЗАЦ",
        [r"5\.\s*ЛЕКСИЧЕСКИЕ", r"6\.\s*ЧТО\s+НУЖНО"],
    )
    patterns_block = _extract_section(
        raw_text,
        r"5\.\s*ЛЕКСИЧЕСКИЕ\s+И\s+СИНТАКСИЧЕСКИЕ\s+ПАТТЕРНЫ",
        [r"6\.\s*ЧТО\s+НУЖНО", r"7\.\s*ЧЕГО\s+НЕЛЬЗЯ"],
    )
    do_block = _extract_section(
        raw_text,
        r"6\.\s*ЧТО\s+НУЖНО\s+ДЕЛАТЬ",
        [r"7\.\s*ЧЕГО\s+НЕЛЬЗЯ", r"8\.\s*ШАБЛОН"],
    )
    dont_block = _extract_section(
        raw_text,
        r"7\.\s*ЧЕГО\s+НЕЛЬЗЯ\s+ДЕЛАТЬ",
        [r"8\.\s*ШАБЛОН", r"9\.\s*КРАТКАЯ\s+ИНСТРУКЦИЯ"],
    )
    generation_instruction = _extract_section(
        raw_text,
        r"9\.\s*КРАТКАЯ\s+ИНСТРУКЦИЯ",
        [],
    )
    if not generation_instruction:
        generation_instruction = _extract_section(raw_text, r"8\.\s*ШАБЛОН\s+ДЛЯ\s+ГЕНЕРАЦИИ", [])

    return {
        "outlet_name": outlet_name,
        "headline_logic": headline_logic,
        "lead_logic": lead_logic,
        "typical_patterns": _extract_rules(patterns_block),
        "do_rules": _extract_rules(do_block),
        "dont_rules": _extract_rules(dont_block),
        "generation_instruction": generation_instruction,
        "raw_text_fallback": True,
    }


def parse_step4(raw_text: str, model_name: str, outlet_name: str, event_id: str, scenario_type: str) -> dict:
    payload = _maybe_json(raw_text)
    if isinstance(payload, dict) and isinstance(payload.get("drafts"), list):
        return payload

    variant_patterns = [
        ("базовый", r"ВАРИАНТ\s*1[^\n]*БАЗОВЫЙ"),
        ("осторожный", r"ВАРИАНТ\s*2[^\n]*ОСТОРОЖ"),
        ("более_сильный", r"ВАРИАНТ\s*3[^\n]*СИЛЬН"),
    ]

    markers = []
    for variant_type, pattern in variant_patterns:
        m = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if m:
            markers.append((variant_type, m.start(), m.end()))
    markers.sort(key=lambda x: x[1])

    drafts: list[dict] = []
    best_variant = ""

    for idx, (variant_type, start, end) in enumerate(markers):
        next_start = markers[idx + 1][1] if idx + 1 < len(markers) else len(raw_text)
        block = raw_text[end:next_start]

        headline_match = re.search(r"Заголовок\s*:\s*(.+)", block, flags=re.IGNORECASE)
        lead_match = re.search(r"Лид\s*:\s*(.+)", block, flags=re.IGNORECASE | re.DOTALL)
        why_match = re.search(r"Почему[^:]*:\s*(.+)", block, flags=re.IGNORECASE | re.DOTALL)

        headline = headline_match.group(1).strip() if headline_match else ""

        lead = ""
        if lead_match:
            lead_raw = lead_match.group(1).strip()
            lead = re.split(r"\n\s*Почему[^:]*:", lead_raw, flags=re.IGNORECASE)[0].strip()

        why = ""
        if why_match:
            why = why_match.group(1).strip().splitlines()[0].strip()

        drafts.append(
            {
                "model_name": model_name,
                "outlet_name": outlet_name,
                "event_id": event_id,
                "scenario_type": scenario_type,
                "variant_type": variant_type,
                "headline": headline,
                "lead": lead,
                "why_plausible": why,
                "selected_by_model": False,
            }
        )

    best_block = _extract_section(raw_text, r"ЛУЧШИЙ\s+ВАРИАНТ", [r"ФИНАЛЬНАЯ\s+ВЕРСИЯ"])
    for line in _clean_lines(best_block):
        if line.lower().startswith("какой") and ":" in line:
            best_variant = line.split(":", 1)[1].strip().lower()

    for draft in drafts:
        vt = draft["variant_type"]
        if best_variant and (vt in best_variant or best_variant in vt):
            draft["selected_by_model"] = True

    return {
        "model_name": model_name,
        "outlet_name": outlet_name,
        "event_id": event_id,
        "scenario_type": scenario_type,
        "drafts": drafts,
        "best_variant": best_variant,
        "raw_text_fallback": True,
    }


def parse_step5(raw_text: str, provider: str) -> dict:
    payload = _maybe_json(raw_text)
    if isinstance(payload, dict):
        payload.setdefault("provider", provider)
        return payload

    ranking: list[str] = []
    for line in _clean_lines(raw_text):
        m_place = re.match(r"^\d+\s*место\s*:\s*(.+)$", line, flags=re.IGNORECASE)
        if m_place:
            ranking.append(m_place.group(1).strip())
            continue
        m_numbered = re.match(r"^\d+[.)]\s*(.+)$", line)
        if m_numbered and len(ranking) < 7:
            ranking.append(m_numbered.group(1).strip())

    return {
        "provider": provider,
        "final_review": raw_text.strip(),
        "ranking_candidates": ranking[:10],
        "top3": ranking[:3],
        "raw_text_fallback": True,
    }


def parse_by_step(step: str, raw_text: str, provider: str, context: dict[str, str] | None = None) -> dict:
    context = context or {}
    if step == "step1":
        return parse_step1(raw_text)
    if step == "step2":
        return parse_step2(raw_text, event_id=context.get("event_id", ""))
    if step == "step3":
        return parse_step3(raw_text, outlet_name=context.get("outlet_name", ""))
    if step == "step4":
        return parse_step4(
            raw_text,
            model_name=provider,
            outlet_name=context.get("outlet_name", ""),
            event_id=context.get("event_id", ""),
            scenario_type=context.get("scenario_type", ""),
        )
    if step == "step5":
        return parse_step5(raw_text, provider=provider)
    raise ValueError(f"Неизвестный шаг для парсинга: {step}")
