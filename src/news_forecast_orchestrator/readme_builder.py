from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path


def extract_docx_text(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"<w:p[^>]*>", "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    xml = xml.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    lines = [line.strip() for line in xml.splitlines() if line.strip()]
    return "\n".join(lines)


def build_readme_text(method_text: str) -> str:
    has_prompts = "PROMPT" in method_text.upper()

    lines = [
        "# Система сценарного прогнозирования новостных заголовков",
        "",
        "CLI-оркестратор для прогнозирования деловых новостей по дате, событию и логике конкретного СМИ.",
        "",
        "## Ключевая идея",
        "",
        "Система поддерживает два рабочих контура:",
        "",
        "- API-first (основной): после выбора события и списка СМИ этапы 2–5 выполняются автоматически по API.",
        "- Manual fallback: при отсутствии ключей можно пройти шаги вручную через copy/paste.",
        "",
        "API-ключи не включены в репозиторий по соображениям информационной безопасности и гигиены.",
        "",
        "## Совместимость и интеграция",
        "",
        "Система совместима с внешними интерфейсами:",
        "",
        "- как backend для Telegram/других мессенджер-ботов;",
        "- как сервисный модуль внутри корпоративной/редакционной информационной системы;",
        "- как CLI-пайплайн для исследовательской и редакционной работы.",
        "",
        "## Что делает система",
        "",
        "- Ищет события под заданную дату (шаг 1, OpenAI).",
        "- Строит тренды и сценарии (шаг 2, OpenAI).",
        "- Восстанавливает стиль конкретного СМИ (шаг 3, OpenAI).",
        "- Генерирует заголовки и лиды в OpenAI, DeepSeek и Qwen (шаг 4).",
        "- Проводит внутреннюю редакционную комиссию и ранжирование топ-3 (шаг 5, OpenAI).",
        "- Сохраняет raw/parsed/summary и сравнительные артефакты по сессиям.",
        "",
        "## Пайплайн",
        "",
        "1. `step1` — поиск 8–12 событий-кандидатов.",
        "2. Пользователь выбирает одно или несколько событий (`select-event` / `select-events`).",
        "3. Пользователь задаёт интересующие СМИ.",
        "4. `step2` — анализ повестки и сценариев.",
        "5. `step3` — анализ логики выбранных СМИ.",
        "6. `step4` — генерация вариантов тремя моделями.",
        "7. `step5` — внутренняя редакционная комиссия, ранжирование и финальный топ-3.",
        "8. Ручная экспертная оценка и выбор финальных потенциальных заголовков/лидов для СМИ.",
        "",
        "## Режим после выбора событий",
        "",
        "После шага 1 можно запустить автоматический прогон:",
        "",
        "```bash",
        "python -m news_forecast_orchestrator.cli auto-run \\",
        "  --session <session_id> \\",
        "  --event-ids event_01,event_03 \\",
        "  --outlets \"РБК,Коммерсантъ,Ведомости\"",
        "```",
        "",
        "Автоматически выполняются шаги `step2 -> step3 -> step4 -> step5` и формируется отчёт:",
        "",
        "- `exports/auto_run_report.md`",
        "",
        "## Промпты",
        "",
        "- `prompts/step1_event_search.md`",
        "- `prompts/step2_trend_scenarios.md`",
        "- `prompts/step3_outlet_style.md`",
        "- `prompts/step4_generation.md`",
        "- `prompts/step4_comparison.md`",
        "- `prompts/step5_editorial_committee.md`",
    ]

    if has_prompts:
        lines.append("")
        lines.append("Промпты включают исходную методическую логику и прикладные шаблоны под автоматический пайплайн.")

    lines.extend(
        [
            "",
            "## Структура проекта",
            "",
            "```text",
            ".",
            "├─ README.md",
            "├─ requirements.txt",
            "├─ .env.example",
            "├─ pyproject.toml",
            "├─ settings.example.toml",
            "├─ prompts/",
            "├─ data/",
            "├─ src/news_forecast_orchestrator/",
            "└─ docs/architecture.md",
            "```",
            "",
            "## Быстрый старт",
            "",
            "```bash",
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -r requirements.txt",
            "pip install -e .",
            "```",
            "",
            "## Ключи API",
            "",
            "1. Скопируйте `.env.example` в `.env`.",
            "2. Заполните `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`.",
            "3. При необходимости укажите `*_BASE_URL` и `*_MODEL`.",
            "",
            "Для полного автоматического прогона нужны все три ключа генерации и ключ OpenAI для шага 5.",
        ]
    )

    return "\n".join(lines)


def build_readme(docx_path: Path, output_path: Path) -> Path:
    method_text = extract_docx_text(docx_path)
    readme_text = build_readme_text(method_text)
    output_path.write_text(readme_text, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка README на основе .docx методики")
    parser.add_argument("--docx", required=True, help="Путь к исходному .docx")
    parser.add_argument("--output", default="README.md", help="Путь для итогового README")
    args = parser.parse_args()

    output = build_readme(Path(args.docx), Path(args.output))
    print(f"README сформирован: {output}")


if __name__ == "__main__":
    main()
