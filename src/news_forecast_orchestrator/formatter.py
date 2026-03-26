from __future__ import annotations


def format_step1_summary(parsed: dict) -> str:
    candidates = parsed.get("candidates", [])
    lines = ["# Резюме шага 1", "", f"Найдено кандидатов: {len(candidates)}", ""]
    for item in candidates[:5]:
        lines.append(f"- `{item.get('id', '')}` {item.get('title', '')} (уверенность: {item.get('confidence', 'н/д')})")
    best = parsed.get("best_for_outlets", {})
    if best:
        lines.extend([
            "",
            "Рекомендованные кандидаты по СМИ:",
            f"- РБК: {', '.join(best.get('РБК', [])) or 'нет данных'}",
            f"- Коммерсантъ: {', '.join(best.get('Коммерсантъ', [])) or 'нет данных'}",
            f"- Ведомости: {', '.join(best.get('Ведомости', [])) or 'нет данных'}",
        ])
    lines.extend(
        [
            "",
            "Следующее действие: выберите событие командой `select-event` и запустите `step2`.",
        ]
    )
    return "\n".join(lines)


def format_step2_summary(parsed: dict) -> str:
    trends = parsed.get("trends", [])
    lines = ["# Резюме шага 2", "", "Выделены сценарии:"]
    lines.append(f"- Базовый: {'есть' if parsed.get('base_scenario') else 'нет'}")
    lines.append(f"- Осторожный: {'есть' if parsed.get('cautious_scenario') else 'нет'}")
    lines.append(f"- Более сильный: {'есть' if parsed.get('stronger_scenario') else 'нет'}")
    if trends:
        lines.append("")
        lines.append("Ключевые тренды:")
        for trend in trends[:6]:
            lines.append(f"- {trend}")
    selected = parsed.get("selected_scenario", "")
    lines.extend(
        [
            "",
            f"Рекомендованный сценарий из ответа: {selected or 'не указан'}",
            "Следующее действие: выберите сценарий (`select-scenario`) и запустите `step3`.",
        ]
    )
    return "\n".join(lines)


def format_step3_summary(parsed: dict) -> str:
    lines = ["# Резюме шага 3", ""]
    lines.append(f"СМИ: {parsed.get('outlet_name', 'не указано')}")
    lines.append(f"Правил do: {len(parsed.get('do_rules', []))}")
    lines.append(f"Правил don't: {len(parsed.get('dont_rules', []))}")

    instruction = parsed.get("generation_instruction", "").strip()
    if instruction:
        preview = instruction.splitlines()[:5]
        lines.extend(["", "Фрагмент инструкции для генерации:"])
        lines.extend([f"- {line}" for line in preview if line.strip()])

    lines.extend(
        [
            "",
            "Следующее действие: запустите `step4` и соберите ответы OpenAI, DeepSeek и Qwen.",
        ]
    )
    return "\n".join(lines)


def format_step4_summary(parsed: dict) -> str:
    model = parsed.get("model_name", "unknown")
    drafts = parsed.get("drafts", [])
    ingested_at = parsed.get("ingested_at", "не указано")
    lines = [
        f"# Резюме шага 4 ({model})",
        "",
        f"Модель: {model}",
        f"Время ответа: {ingested_at}",
        f"Получено вариантов: {len(drafts)}",
        "",
    ]
    for draft in drafts:
        marker = " [ЛУЧШИЙ]" if draft.get("selected_by_model") else ""
        lines.append(f"- {draft.get('variant_type', '')}: {draft.get('headline', '')}{marker}")
    lines.append("")
    lines.append("Следующее действие: загрузите ответы остальных моделей и выполните `compare`.")
    return "\n".join(lines)


def format_step5_summary(parsed: dict) -> str:
    top3 = parsed.get("top3", [])
    lines = ["# Резюме шага 5 (редакционная комиссия)", ""]
    if top3:
        lines.append("Топ-3 варианта по версии комиссии:")
        for idx, item in enumerate(top3, start=1):
            lines.append(f"- {idx}. {item}")
    else:
        lines.append("Топ-3 не удалось извлечь автоматически. Проверьте raw-ответ.")
    lines.append("")
    lines.append("Следующее действие: выполните ручную экспертную оценку и выберите финальные варианты.")
    return "\n".join(lines)


def format_summary(step: str, parsed: dict) -> str:
    if step == "step1":
        return format_step1_summary(parsed)
    if step == "step2":
        return format_step2_summary(parsed)
    if step == "step3":
        return format_step3_summary(parsed)
    if step == "step4":
        return format_step4_summary(parsed)
    if step == "step5":
        return format_step5_summary(parsed)
    return "# Резюме\n\nНет форматтера для указанного шага."


def format_next_instruction(step: str, provider: str = "openai") -> str:
    if step == "step1":
        return (
            "Что дальше:\n"
            "1. Скопируйте prompt из файла `step1/prompt_openai.txt`.\n"
            "2. Отправьте в OpenAI/ChatGPT.\n"
            "3. Верните ответ через `ingest-response --step step1 --provider openai`."
        )
    if step == "step2":
        return (
            "Что дальше:\n"
            "1. Скопируйте prompt из `step2/prompt_openai.txt`.\n"
            "2. Отправьте в OpenAI/ChatGPT.\n"
            "3. Верните ответ через `ingest-response --step step2 --provider openai`."
        )
    if step == "step3":
        return (
            "Что дальше:\n"
            "1. Скопируйте prompt из `step3/prompt_openai.txt`.\n"
            "2. Отправьте в OpenAI/ChatGPT.\n"
            "3. Верните ответ через `ingest-response --step step3 --provider openai`."
        )
    if step == "step4":
        return (
            "Что дальше:\n"
            "1. Отправьте `prompt_openai.txt`, `prompt_deepseek.txt`, `prompt_qwen.txt` в соответствующие модели.\n"
            "2. Загрузите каждый ответ через `ingest-response --step step4 --provider <openai|deepseek|qwen>`.\n"
            "3. Выполните `compare` для единого сравнительного блока."
        )
    if step == "step5":
        return (
            "Что дальше:\n"
            "1. Отправьте `step5/prompt_openai.txt` в OpenAI.\n"
            "2. Загрузите ответ через `ingest-response --step step5 --provider openai`.\n"
            "3. Проведите ручную экспертную оценку и выберите финальный набор."
        )
    return "Что дальше: продолжайте следующий шаг пайплайна."
