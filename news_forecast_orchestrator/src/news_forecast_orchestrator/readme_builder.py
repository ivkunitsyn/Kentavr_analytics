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
    source_note = "Методика формирования прогнозов новостных заголовков"
    has_prompts = "PROMPT" in method_text.upper()

    lines = [
        "# Система сценарного прогнозирования новостных заголовков",
        "",
        "Локальная CLI-система пошагового сценарного прогнозирования новостных заголовков и лидов для деловых СМИ.",
        "",
        f"README собран на основе методики: **{source_note}**.",
        "",
        "## Что делает система",
        "",
        "- Ищет события под заданную дату (шаг 1, OpenAI).",
        "- Строит тренды и сценарии (шаг 2, OpenAI).",
        "- Восстанавливает стиль конкретного СМИ (шаг 3, OpenAI).",
        "- Генерирует заголовки и лиды в трёх моделях: OpenAI, DeepSeek, Qwen (шаг 4).",
        "- Сохраняет raw/parsed/summary артефакты по сессиям.",
        "- Поддерживает manual-first режим без API-ключей.",
        "",
        "## Режимы работы",
        "",
        "- `manual` (MVP): система выводит промпт, пользователь вручную отправляет его в модель и возвращает ответ через `ingest-response`.",
        "- `api`: если есть ключи, можно вызывать провайдеры напрямую; если ключей нет, система автоматически откатывается к manual-flow.",
        "",
        "## Пайплайн",
        "",
        "1. `step1` — поиск 8–12 событий-кандидатов.",
        "2. `select-event` — выбор события.",
        "3. `step2` — сценарии: базовый, осторожный, более сильный.",
        "4. `select-scenario` — выбор сценария.",
        "5. `step3` — профиль стиля СМИ и правила генерации.",
        "6. `step4` — генерация вариантов OpenAI/DeepSeek/Qwen.",
        "7. `compare` — единый сравнительный блок.",
        "",
        "## Механика передачи между шагами",
        "",
        "1. Система формирует prompt и сохраняет его в папке шага.",
        "2. Пользователь копирует prompt и отправляет в нужную модель.",
        "3. Пользователь возвращает ответ в CLI через `ingest-response`.",
        "4. Система сохраняет raw, parsed, summary и готовит следующий шаг.",
        "",
        "## Промпты",
        "",
        "- `prompts/step1_event_search.md`",
        "- `prompts/step2_trend_scenarios.md`",
        "- `prompts/step3_outlet_style.md`",
        "- `prompts/step4_generation.md`",
        "- `prompts/step4_comparison.md`",
    ]

    if has_prompts:
        lines.append("")
        lines.append("Промпты адаптированы из блока `Рабочие промпты` исходной методики.")

    lines.extend(
        [
            "",
            "## Структура проекта",
            "",
            "```text",
            "news_forecast_orchestrator/",
            "├─ README.md",
            "├─ requirements.txt",
            "├─ .env.example",
            "├─ pyproject.toml",
            "├─ settings.example.toml",
            "├─ prompts/",
            "│  ├─ step1_event_search.md",
            "│  ├─ step2_trend_scenarios.md",
            "│  ├─ step3_outlet_style.md",
            "│  ├─ step4_generation.md",
            "│  └─ step4_comparison.md",
            "├─ data/",
            "│  └─ sessions/<session_id>/",
            "├─ src/news_forecast_orchestrator/",
            "│  ├─ cli.py",
            "│  ├─ config.py",
            "│  ├─ models.py",
            "│  ├─ storage.py",
            "│  ├─ session.py",
            "│  ├─ prompts.py",
            "│  ├─ formatter.py",
            "│  ├─ parser.py",
            "│  ├─ providers/",
            "│  └─ steps/",
            "└─ docs/architecture.md",
            "```",
            "",
            "## Быстрый старт",
            "",
            "```bash",
            "cd news_forecast_orchestrator",
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -r requirements.txt",
            "pip install -e .",
            "```",
            "",
            "Создать сессию:",
            "",
            "```bash",
            "python -m news_forecast_orchestrator.cli new-session --date 2026-04-02",
            "```",
            "",
            "Запуск шагов:",
            "",
            "```bash",
            "python -m news_forecast_orchestrator.cli step1 --session <session_id> --mode manual",
            "python -m news_forecast_orchestrator.cli ingest-response --session <session_id> --step step1 --provider openai",
            "python -m news_forecast_orchestrator.cli select-event --session <session_id> --event-id event_03",
            "python -m news_forecast_orchestrator.cli step2 --session <session_id> --mode manual",
            "python -m news_forecast_orchestrator.cli select-scenario --session <session_id> --scenario base",
            "python -m news_forecast_orchestrator.cli step3 --session <session_id> --outlet \"Коммерсантъ\" --mode manual",
            "python -m news_forecast_orchestrator.cli step4 --session <session_id> --mode manual",
            "python -m news_forecast_orchestrator.cli compare --session <session_id>",
            "```",
            "",
            "## Артефакты сессии",
            "",
            "Все файлы хранятся в `data/sessions/<session_id>/`.",
            "",
            "- `step1/`: prompt, raw, parsed, summary",
            "- `step2/`: input_from_step1, prompt, raw, parsed, summary",
            "- `step3/`: input_from_step2, prompt, raw, parsed, summary",
            "- `step4/`: prompt_* и response_* для трёх моделей, `comparison.md`",
            "- `exports/`: итоговые экспортные файлы",
            "",
            "## Ключи API",
            "",
            "1. Скопируйте `.env.example` в `.env`.",
            "2. Заполните `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`.",
            "3. При необходимости укажите `*_BASE_URL` и `*_MODEL`.",
            "",
            "Без ключей система остаётся полностью рабочей в manual-режиме.",
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
