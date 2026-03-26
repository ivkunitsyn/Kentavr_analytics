from __future__ import annotations

import re
from itertools import combinations


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[A-Za-zА-Яа-я0-9]+", text.lower())
    stop = {
        "и", "в", "на", "по", "с", "к", "для", "что", "как", "из", "или", "а", "но", "же", "это", "все", "уже",
        "the", "and", "for", "with", "from", "that", "this", "was",
    }
    return {w for w in words if len(w) > 2 and w not in stop}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _extract_headlines(parsed: dict) -> list[str]:
    headlines = []
    for draft in parsed.get("drafts", []):
        if draft.get("headline"):
            headlines.append(draft["headline"])
    return headlines


def _extract_leads(parsed: dict) -> list[str]:
    leads = []
    for draft in parsed.get("drafts", []):
        if draft.get("lead"):
            leads.append(draft["lead"])
    return leads


def build_comparison_markdown(outputs_by_provider: dict[str, dict]) -> str:
    providers = [p for p in ("openai", "deepseek", "qwen") if p in outputs_by_provider]

    lines = ["# Сравнение результатов шага 4", ""]
    if not providers:
        lines.append("Нет данных для сравнения.")
        return "\n".join(lines)

    lines.append("## По моделям")
    for provider in providers:
        parsed = outputs_by_provider[provider]
        drafts = parsed.get("drafts", [])
        ingested_at = parsed.get("ingested_at", "не указано")
        lines.append("")
        lines.append(f"### {provider.upper()}")
        lines.append(f"- Время ответа: {ingested_at}")
        for draft in drafts:
            best_mark = " [лучший по версии модели]" if draft.get("selected_by_model") else ""
            lines.append(f"- {draft.get('variant_type', '')}: {draft.get('headline', '')}{best_mark}")
            lines.append(f"  Лид: {draft.get('lead', '')}")

    lines.append("")
    lines.append("## Совпадения")
    headline_token_sets = {}
    lead_token_sets = {}
    for provider in providers:
        headlines = " ".join(_extract_headlines(outputs_by_provider[provider]))
        leads = " ".join(_extract_leads(outputs_by_provider[provider]))
        headline_token_sets[provider] = _tokens(headlines)
        lead_token_sets[provider] = _tokens(leads)

    for a, b in combinations(providers, 2):
        h_sim = _jaccard(headline_token_sets[a], headline_token_sets[b])
        l_sim = _jaccard(lead_token_sets[a], lead_token_sets[b])
        lines.append(f"- {a.upper()} vs {b.upper()}: близость заголовков {h_sim:.2f}, близость лидов {l_sim:.2f}")

    common_headline = set.intersection(*(headline_token_sets[p] for p in providers)) if providers else set()
    common_lead = set.intersection(*(lead_token_sets[p] for p in providers)) if providers else set()

    lines.append("")
    lines.append("## Устойчивые формулировки")
    lines.append(f"- Общие токены заголовков: {', '.join(sorted(common_headline)[:20]) or 'не выявлены'}")
    lines.append(f"- Общие токены лидов: {', '.join(sorted(common_lead)[:20]) or 'не выявлены'}")

    lines.append("")
    lines.append("## Расхождения")
    lines.append("- Отметьте варианты с минимальной пересекаемостью как наиболее различающиеся по углу подачи.")
    lines.append("- Проверьте, где одна модель добавляет лишнюю конкретику, которой нет в сценарии.")

    lines.append("")
    lines.append("## Рекомендация")
    winner = max(
        providers,
        key=lambda p: len(outputs_by_provider[p].get("drafts", [])),
    )
    lines.append(f"- Базовый технический победитель по полноте структурированного ответа: {winner.upper()}.")
    lines.append("- Финальный выбор лучше сделать вручную через `select-winner` после редакторской проверки.")

    return "\n".join(lines)
