# Система сценарного прогнозирования новостных заголовков

Локальная CLI-система пошагового сценарного прогнозирования новостных заголовков и лидов для деловых СМИ.

README собран на основе методики: **Методика формирования прогнозов новостных заголовков**.

## Что делает система

- Ищет события под заданную дату (шаг 1, OpenAI).
- Строит тренды и сценарии (шаг 2, OpenAI).
- Восстанавливает стиль конкретного СМИ (шаг 3, OpenAI).
- Генерирует заголовки и лиды в трёх моделях: OpenAI, DeepSeek, Qwen (шаг 4).
- Сохраняет raw/parsed/summary артефакты по сессиям.
- Поддерживает manual-first режим без API-ключей.

## Режимы работы

- `manual` (MVP): система выводит промпт, пользователь вручную отправляет его в модель и возвращает ответ через `ingest-response`.
- `api`: если есть ключи, можно вызывать провайдеры напрямую; если ключей нет, система автоматически откатывается к manual-flow.

## Пайплайн

1. `step1` — поиск 8–12 событий-кандидатов.
2. `select-event` — выбор события.
3. `step2` — сценарии: базовый, осторожный, более сильный.
4. `select-scenario` — выбор сценария.
5. `step3` — профиль стиля СМИ и правила генерации.
6. `step4` — генерация вариантов OpenAI/DeepSeek/Qwen.
7. `compare` — единый сравнительный блок.

## Механика передачи между шагами

1. Система формирует prompt и сохраняет его в папке шага.
2. Пользователь копирует prompt и отправляет в нужную модель.
3. Пользователь возвращает ответ в CLI через `ingest-response`.
4. Система сохраняет raw, parsed, summary и готовит следующий шаг.

## Промпты

- `prompts/step1_event_search.md`
- `prompts/step2_trend_scenarios.md`
- `prompts/step3_outlet_style.md`
- `prompts/step4_generation.md`
- `prompts/step4_comparison.md`

Промпты адаптированы из блока `Рабочие промпты` исходной методики.

## Структура проекта

```text
news_forecast_orchestrator/
├─ README.md
├─ requirements.txt
├─ .env.example
├─ pyproject.toml
├─ settings.example.toml
├─ prompts/
│  ├─ step1_event_search.md
│  ├─ step2_trend_scenarios.md
│  ├─ step3_outlet_style.md
│  ├─ step4_generation.md
│  └─ step4_comparison.md
├─ data/
│  └─ sessions/<session_id>/
├─ src/news_forecast_orchestrator/
│  ├─ cli.py
│  ├─ config.py
│  ├─ models.py
│  ├─ storage.py
│  ├─ session.py
│  ├─ prompts.py
│  ├─ formatter.py
│  ├─ parser.py
│  ├─ providers/
│  └─ steps/
└─ docs/architecture.md
```

## Быстрый старт

```bash
cd news_forecast_orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Создать сессию:

```bash
python -m news_forecast_orchestrator.cli new-session --date 2026-04-02
```

Запуск шагов:

```bash
python -m news_forecast_orchestrator.cli step1 --session <session_id> --mode manual
python -m news_forecast_orchestrator.cli ingest-response --session <session_id> --step step1 --provider openai
python -m news_forecast_orchestrator.cli select-event --session <session_id> --event-id event_03
python -m news_forecast_orchestrator.cli step2 --session <session_id> --mode manual
python -m news_forecast_orchestrator.cli select-scenario --session <session_id> --scenario base
python -m news_forecast_orchestrator.cli step3 --session <session_id> --outlet "Коммерсантъ" --mode manual
python -m news_forecast_orchestrator.cli step4 --session <session_id> --mode manual
python -m news_forecast_orchestrator.cli compare --session <session_id>
```

## Артефакты сессии

Все файлы хранятся в `data/sessions/<session_id>/`.

- `step1/`: prompt, raw, parsed, summary
- `step2/`: input_from_step1, prompt, raw, parsed, summary
- `step3/`: input_from_step2, prompt, raw, parsed, summary
- `step4/`: prompt_* и response_* для трёх моделей, `comparison.md`
- `exports/`: итоговые экспортные файлы

## Ключи API

1. Скопируйте `.env.example` в `.env`.
2. Заполните `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`.
3. При необходимости укажите `*_BASE_URL` и `*_MODEL`.

Без ключей система остаётся полностью рабочей в manual-режиме.
