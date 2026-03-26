# Система сценарного прогнозирования новостных заголовков

CLI-оркестратор для прогнозирования новостей по дате, событию и логике конкретного СМИ.

## Ключевая идея

Система поддерживает два рабочих контура:

- API-first (основной): после выбора события и списка СМИ этапы 2–5 выполняются автоматически по API.
- Manual fallback: при отсутствии ключей можно пройти шаги вручную через copy/paste.

API-ключи не включены в репозиторий по соображениям информационной безопасности и гигиены.

## Совместимость и интеграция

Система совместима с внешними интерфейсами:

- как backend для Telegram/других мессенджер-ботов;
- как сервисный модуль внутри корпоративной/редакционной информационной системы;
- как CLI-пайплайн для исследовательской и редакционной работы.

## Что делает система

- Ищет события под заданную дату (шаг 1, OpenAI).
- Строит тренды и сценарии (шаг 2, OpenAI).
- Восстанавливает стиль конкретного СМИ (шаг 3, OpenAI).
- Генерирует заголовки и лиды в OpenAI, DeepSeek и Qwen (шаг 4).
- Проводит внутреннюю редакционную комиссию и ранжирование топ-3 (шаг 5, OpenAI).
- Сохраняет raw/parsed/summary и сравнительные артефакты по сессиям.

## Пайплайн

1. `step1` — поиск 8–12 событий-кандидатов.
2. Пользователь выбирает одно или несколько событий (`select-event` / `select-events`).
3. Пользователь задаёт интересующие СМИ.
4. `step2` — анализ повестки и сценариев.
5. `step3` — анализ логики выбранных СМИ.
6. `step4` — генерация вариантов тремя моделями.
7. `step5` — внутренняя редакционная комиссия, ранжирование и финальный топ-3.
8. Ручная экспертная оценка и выбор финальных потенциальных заголовков/лидов для СМИ.

## Режим после выбора событий

После шага 1 можно запустить автоматический прогон:

```bash
python -m news_forecast_orchestrator.cli auto-run \
  --session <session_id> \
  --event-ids event_01,event_03 \
  --outlets "РБК,Коммерсантъ,Ведомости"
```

Автоматически выполняются шаги `step2 -> step3 -> step4 -> step5` и формируется отчёт:

- `exports/auto_run_report.md`

## Промпты

- `prompts/step1_event_search.md`
- `prompts/step2_trend_scenarios.md`
- `prompts/step3_outlet_style.md`
- `prompts/step4_generation.md`
- `prompts/step4_comparison.md`
- `prompts/step5_editorial_committee.md`

## Структура проекта

```text
.
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
│  ├─ step4_comparison.md
│  └─ step5_editorial_committee.md
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
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Создать сессию:

```bash
python -m news_forecast_orchestrator.cli new-session --date 2026-04-02
```

Шаг 1:

```bash
python -m news_forecast_orchestrator.cli step1 --session <session_id> --mode api
```

Если нужен ручной ввод ответа шага 1:

```bash
python -m news_forecast_orchestrator.cli ingest-response --session <session_id> --step step1 --provider openai
```

Выбор нескольких событий:

```bash
python -m news_forecast_orchestrator.cli select-events --session <session_id> --event-ids event_01,event_03
```

Автоматический прогон шагов 2–5:

```bash
python -m news_forecast_orchestrator.cli auto-run \
  --session <session_id> \
  --event-ids event_01,event_03 \
  --outlets "РБК,Коммерсантъ"
```

## Артефакты сессии

Все файлы хранятся в `data/sessions/<session_id>/`.

- `step1/`: prompt, raw, parsed, summary, выбранные события
- `step2/`: входы и результаты сценариев (включая `runs/<event_id>/`)
- `step3/`: профиль стиля СМИ (включая `runs/<event_id>__<outlet>/`)
- `step4/`: prompts и ответы трёх моделей, `comparison.md` (включая `runs/`)
- `step5/`: финальная комиссия и ранжирование топ-3 (включая `runs/`)
- `exports/`: итоговые отчёты и финальный выбор

## Ключи API

1. Скопируйте `.env.example` в `.env`.
2. Заполните `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`.
3. При необходимости укажите `*_BASE_URL` и `*_MODEL`.

Для полного автоматического прогона нужны все три ключа генерации и ключ OpenAI для шага 5.
