from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .compare_outputs import build_comparison_markdown
from .config import AppSettings, load_settings
from .formatter import format_next_instruction, format_summary
from .parser import parse_by_step
from .prompts import PromptLibrary
from .providers import provider_factory
from .providers.base import ProviderError
from .readme_builder import build_readme
from .session import SessionService
from .steps.step1_event_search import prepare_step1_prompt
from .steps.step2_trend_scenarios import prepare_step2_prompt, resolve_selected_scenario
from .steps.step3_outlet_style import prepare_step3_prompt
from .steps.step4_generation import prepare_step4_prompts
from .storage import SessionStorage


VALID_STEPS = {"step1", "step2", "step3", "step4"}
VALID_PROVIDERS = {"openai", "deepseek", "qwen"}
VALID_SCENARIOS = {"base", "cautious", "stronger"}


def _bootstrap(config_path: str | None = None) -> tuple[AppSettings, SessionStorage, SessionService, PromptLibrary]:
    settings = load_settings(config_path=config_path)
    storage = SessionStorage(settings.paths.sessions_dir)
    sessions = SessionService(storage)
    prompts = PromptLibrary(settings.paths.prompts_dir)
    return settings, storage, sessions, prompts


def _load_required_json(storage: SessionStorage, session_id: str, relative_path: str, hint: str) -> dict:
    if not storage.exists(session_id, relative_path):
        raise SystemExit(f"Не найден файл `{relative_path}`. Сначала выполните: {hint}")
    return storage.read_json(session_id, relative_path)


def _save_ingest(
    storage: SessionStorage,
    sessions: SessionService,
    manifest,
    *,
    step: str,
    provider: str,
    raw_text: str,
    context: dict[str, str] | None = None,
) -> dict:
    step_dir = step
    raw_rel = f"{step_dir}/response_{provider}_raw.txt"
    parsed_rel = f"{step_dir}/response_{provider}_parsed.json"

    storage.write_text(manifest.session_id, raw_rel, raw_text)
    parsed = parse_by_step(step, raw_text, provider, context=context)
    parsed["provider"] = provider
    parsed["step"] = step
    parsed["ingested_at"] = datetime.now().isoformat(timespec="seconds")
    storage.write_json(manifest.session_id, parsed_rel, parsed)

    sessions.register_file(manifest, raw_rel)
    sessions.register_file(manifest, parsed_rel)

    summary_text = format_summary(step, parsed)
    if step in {"step1", "step2", "step3"}:
        summary_rel = f"{step_dir}/summary.md"
    else:
        summary_rel = f"{step_dir}/summary_{provider}.md"
    storage.write_text(manifest.session_id, summary_rel, summary_text)
    sessions.register_file(manifest, summary_rel)

    sessions.update_step(manifest, f"{step}_response_ingested")
    sessions.save_manifest(manifest)

    print(f"Ответ сохранён: {raw_rel}")
    print(f"Parsed сохранён: {parsed_rel}")
    print(f"Summary сохранён: {summary_rel}")
    print("\n" + summary_text)
    return parsed


def _ingest_from_api_if_possible(
    settings: AppSettings,
    storage: SessionStorage,
    sessions: SessionService,
    manifest,
    *,
    step: str,
    provider: str,
    prompt: str,
    context: dict[str, str] | None = None,
) -> bool:
    api_provider = provider_factory(provider, settings)
    if not api_provider.is_available:
        print(
            f"`{provider}` не настроен (нет ключа). Остаёмся в manual-режиме: "
            f"скопируйте prompt и верните ответ через ingest-response."
        )
        return False

    try:
        raw_text = api_provider.generate(prompt)
    except ProviderError as exc:
        print(f"Ошибка API-вызова {provider}: {exc}")
        print("Переход в manual-режим.")
        return False

    _save_ingest(
        storage,
        sessions,
        manifest,
        step=step,
        provider=provider,
        raw_text=raw_text,
        context=context,
    )
    return True


def _read_user_response(input_file: str | None) -> str:
    if input_file:
        path = Path(input_file)
        if not path.exists():
            raise SystemExit(f"Файл не найден: {path}")
        return path.read_text(encoding="utf-8")

    if sys.stdin.isatty():
        print("Вставьте ответ модели и завершите ввод Ctrl-D (macOS/Linux) или Ctrl-Z Enter (Windows):")
    return sys.stdin.read()


def cmd_new_session(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.create_session(
        target_date=args.date,
        country=args.country,
        topic=args.topic or "",
        chosen_outlet=args.outlet or "",
    )
    print(f"Создана сессия: {manifest.session_id}")
    print(f"Папка сессии: {storage.session_dir(manifest.session_id)}")


def cmd_step1(args: argparse.Namespace) -> None:
    settings, storage, sessions, prompts = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    prompt = prepare_step1_prompt(manifest, prompts)
    prompt_rel = "step1/prompt_openai.txt"
    storage.write_text(manifest.session_id, prompt_rel, prompt)
    sessions.register_file(manifest, prompt_rel)
    sessions.update_step(manifest, "step1_prompt_ready")
    sessions.save_manifest(manifest)

    print(f"Prompt сохранён: {prompt_rel}")
    print("\n=== PROMPT STEP1 (OPENAI) ===\n")
    print(prompt)
    print("\n" + format_next_instruction("step1"))

    if args.mode == "api":
        _ingest_from_api_if_possible(
            settings,
            storage,
            sessions,
            manifest,
            step="step1",
            provider="openai",
            prompt=prompt,
            context={},
        )


def cmd_select_event(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step1/response_openai_parsed.json",
        "step1 + ingest-response для step1",
    )

    candidates = parsed.get("candidates", [])
    if not any(item.get("id") == args.event_id for item in candidates):
        available = ", ".join(item.get("id", "") for item in candidates) or "пусто"
        raise SystemExit(f"Событие `{args.event_id}` не найдено. Доступные ID: {available}")

    sessions.set_chosen_event(manifest, args.event_id)
    sessions.update_step(manifest, "event_selected")
    storage.write_text(manifest.session_id, "step1/selected_event.txt", args.event_id)
    sessions.register_file(manifest, "step1/selected_event.txt")
    sessions.save_manifest(manifest)

    print(f"Выбрано событие: {args.event_id}")


def cmd_step2(args: argparse.Namespace) -> None:
    settings, storage, sessions, prompts = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)
    if not manifest.chosen_event:
        raise SystemExit("Сначала выберите событие: `select-event --event-id ...`")

    step1_parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step1/response_openai_parsed.json",
        "step1 + ingest-response для step1",
    )

    prompt, event_payload = prepare_step2_prompt(
        manifest,
        prompts,
        step1_parsed,
        user_notes=args.notes or "",
    )

    storage.write_json(manifest.session_id, "step2/input_from_step1.json", event_payload or {})
    storage.write_text(manifest.session_id, "step2/prompt_openai.txt", prompt)
    sessions.register_file(manifest, "step2/input_from_step1.json")
    sessions.register_file(manifest, "step2/prompt_openai.txt")
    sessions.update_step(manifest, "step2_prompt_ready")
    sessions.save_manifest(manifest)

    print("Prompt step2 сохранён: step2/prompt_openai.txt")
    print("\n=== PROMPT STEP2 (OPENAI) ===\n")
    print(prompt)
    print("\n" + format_next_instruction("step2"))

    if args.mode == "api":
        _ingest_from_api_if_possible(
            settings,
            storage,
            sessions,
            manifest,
            step="step2",
            provider="openai",
            prompt=prompt,
            context={"event_id": manifest.chosen_event},
        )


def cmd_select_scenario(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    scenario = args.scenario.lower()
    if scenario not in VALID_SCENARIOS:
        raise SystemExit("Сценарий должен быть одним из: base | cautious | stronger")

    parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step2/response_openai_parsed.json",
        "step2 + ingest-response для step2",
    )

    selected_text = resolve_selected_scenario(parsed, scenario)
    if not selected_text:
        print("Внимание: выбранный сценарий не найден в parsed-файле, но выбор сохранён в манифесте.")

    parsed["selected_scenario"] = scenario
    storage.write_json(manifest.session_id, "step2/response_openai_parsed.json", parsed)
    storage.write_text(manifest.session_id, "step2/selected_scenario.txt", scenario)

    sessions.set_chosen_scenario(manifest, scenario)
    sessions.register_file(manifest, "step2/selected_scenario.txt")
    sessions.update_step(manifest, "scenario_selected")
    sessions.save_manifest(manifest)

    print(f"Выбран сценарий: {scenario}")


def cmd_step3(args: argparse.Namespace) -> None:
    settings, storage, sessions, prompts = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    if args.outlet:
        sessions.set_chosen_outlet(manifest, args.outlet)
    if not manifest.chosen_outlet:
        raise SystemExit("Для step3 нужен outlet. Передайте --outlet или задайте его в сессии.")

    step1_parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step1/response_openai_parsed.json",
        "step1 + ingest-response для step1",
    )
    step2_parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step2/response_openai_parsed.json",
        "step2 + ingest-response для step2",
    )

    prompt, input_payload = prepare_step3_prompt(manifest, prompts, step1_parsed, step2_parsed)

    storage.write_json(manifest.session_id, "step3/input_from_step2.json", input_payload)
    storage.write_text(manifest.session_id, "step3/prompt_openai.txt", prompt)
    sessions.register_file(manifest, "step3/input_from_step2.json")
    sessions.register_file(manifest, "step3/prompt_openai.txt")
    sessions.update_step(manifest, "step3_prompt_ready")
    sessions.save_manifest(manifest)

    print("Prompt step3 сохранён: step3/prompt_openai.txt")
    print("\n=== PROMPT STEP3 (OPENAI) ===\n")
    print(prompt)
    print("\n" + format_next_instruction("step3"))

    if args.mode == "api":
        _ingest_from_api_if_possible(
            settings,
            storage,
            sessions,
            manifest,
            step="step3",
            provider="openai",
            prompt=prompt,
            context={"outlet_name": manifest.chosen_outlet},
        )


def cmd_step4(args: argparse.Namespace) -> None:
    settings, storage, sessions, prompts = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    if not manifest.chosen_outlet:
        raise SystemExit("Сначала задайте outlet (через step3 --outlet ...).")
    if not manifest.chosen_event:
        raise SystemExit("Сначала выберите событие через select-event.")

    step1_parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step1/response_openai_parsed.json",
        "step1 + ingest-response для step1",
    )
    step2_parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step2/response_openai_parsed.json",
        "step2 + ingest-response для step2",
    )
    step3_parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step3/response_openai_parsed.json",
        "step3 + ingest-response для step3",
    )

    prompts_by_provider, input_payload = prepare_step4_prompts(
        manifest,
        prompts,
        step1_parsed,
        step2_parsed,
        step3_parsed,
    )

    storage.write_json(manifest.session_id, "step4/input_from_step3.json", input_payload)
    sessions.register_file(manifest, "step4/input_from_step3.json")

    for provider, prompt in prompts_by_provider.items():
        rel = f"step4/prompt_{provider}.txt"
        storage.write_text(manifest.session_id, rel, prompt)
        sessions.register_file(manifest, rel)

    sessions.update_step(manifest, "step4_prompts_ready")
    sessions.save_manifest(manifest)

    print("Prompt-файлы сохранены:")
    print("- step4/prompt_openai.txt")
    print("- step4/prompt_deepseek.txt")
    print("- step4/prompt_qwen.txt")

    if args.mode == "manual":
        print("\n" + format_next_instruction("step4"))
        return

    context = {
        "outlet_name": manifest.chosen_outlet,
        "event_id": manifest.chosen_event,
        "scenario_type": manifest.chosen_scenario or "base",
    }
    for provider in ("openai", "deepseek", "qwen"):
        print(f"\n--- API попытка для {provider} ---")
        _ingest_from_api_if_possible(
            settings,
            storage,
            sessions,
            manifest,
            step="step4",
            provider=provider,
            prompt=prompts_by_provider[provider],
            context=context,
        )

    _build_and_save_comparison(storage, sessions, manifest)


def _load_step4_outputs(storage: SessionStorage, session_id: str) -> dict[str, dict]:
    outputs: dict[str, dict] = {}
    for provider in ("openai", "deepseek", "qwen"):
        rel = f"step4/response_{provider}_parsed.json"
        if storage.exists(session_id, rel):
            outputs[provider] = storage.read_json(session_id, rel)
    return outputs


def _build_and_save_comparison(storage: SessionStorage, sessions: SessionService, manifest) -> Path:
    outputs = _load_step4_outputs(storage, manifest.session_id)
    if not outputs:
        raise SystemExit("Для сравнения нет parsed-файлов шага 4.")

    comparison = build_comparison_markdown(outputs)
    rel = "step4/comparison.md"
    path = storage.write_text(manifest.session_id, rel, comparison)
    sessions.register_file(manifest, rel)
    sessions.update_step(manifest, "step4_compared")
    sessions.save_manifest(manifest)
    return path


def cmd_compare(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)
    path = _build_and_save_comparison(storage, sessions, manifest)
    print(f"Сравнение сохранено: {path}")
    print(path.read_text(encoding="utf-8"))


def cmd_ingest_response(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    if args.step not in VALID_STEPS:
        raise SystemExit(f"Неизвестный шаг: {args.step}")
    provider = args.provider.lower()
    if provider not in VALID_PROVIDERS:
        raise SystemExit("Провайдер должен быть одним из: openai | deepseek | qwen")
    if args.step in {"step1", "step2", "step3"} and provider != "openai":
        raise SystemExit("Для шагов 1–3 разрешён только provider=openai.")

    raw_text = _read_user_response(args.input_file)
    if not raw_text.strip():
        raise SystemExit("Пустой ввод. Нечего сохранять.")

    context = {
        "outlet_name": manifest.chosen_outlet,
        "event_id": manifest.chosen_event,
        "scenario_type": manifest.chosen_scenario or "base",
    }

    _save_ingest(
        storage,
        sessions,
        manifest,
        step=args.step,
        provider=provider,
        raw_text=raw_text,
        context=context,
    )

    if args.step == "step4":
        outputs = _load_step4_outputs(storage, manifest.session_id)
        if len(outputs) >= 2:
            path = _build_and_save_comparison(storage, sessions, manifest)
            print(f"\nАвтообновлено сравнение: {path}")


def cmd_status(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)
    print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))

    print("\nНаличие ключевых артефактов:")
    checks = [
        "step1/response_openai_parsed.json",
        "step2/response_openai_parsed.json",
        "step3/response_openai_parsed.json",
        "step4/response_openai_parsed.json",
        "step4/response_deepseek_parsed.json",
        "step4/response_qwen_parsed.json",
        "step4/comparison.md",
    ]
    for rel in checks:
        print(f"- {rel}: {'OK' if storage.exists(manifest.session_id, rel) else 'нет'}")


def cmd_select_winner(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    provider = args.provider.lower()
    if provider not in VALID_PROVIDERS:
        raise SystemExit("provider должен быть: openai | deepseek | qwen")
    if args.variant not in VALID_SCENARIOS:
        raise SystemExit("variant должен быть: base | cautious | stronger")

    parsed = _load_required_json(
        storage,
        manifest.session_id,
        f"step4/response_{provider}_parsed.json",
        "step4 + ingest-response для нужного провайдера",
    )

    target_map = {
        "base": "базовый",
        "cautious": "осторожный",
        "stronger": "более_сильный",
    }
    target_variant = target_map[args.variant]

    draft = None
    for item in parsed.get("drafts", []):
        if item.get("variant_type") == target_variant:
            draft = item
            break

    if not draft:
        raise SystemExit("Не найден выбранный вариант в parsed-файле.")

    export = [
        "# Финальный выбранный вариант",
        "",
        f"- Сессия: {manifest.session_id}",
        f"- Провайдер: {provider}",
        f"- Вариант: {args.variant}",
        f"- Дата: {manifest.target_date}",
        f"- СМИ: {manifest.chosen_outlet}",
        "",
        "## Заголовок",
        draft.get("headline", ""),
        "",
        "## Лид",
        draft.get("lead", ""),
    ]

    rel = "exports/final_winner.md"
    storage.write_text(manifest.session_id, rel, "\n".join(export))
    sessions.register_file(manifest, rel)
    sessions.update_step(manifest, "winner_selected")
    sessions.save_manifest(manifest)

    print(f"Финальный выбор сохранён: {rel}")


def cmd_build_readme(args: argparse.Namespace) -> None:
    output = build_readme(Path(args.docx), Path(args.output))
    print(f"README собран: {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI-оркестратор сценарного прогнозирования новостных заголовков и лидов"
    )
    parser.add_argument("--config", default=None, help="Путь к TOML-конфигу (опционально)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new-session", help="Создать новую сессию")
    p_new.add_argument("--date", required=True, help="Целевая дата, например 2026-04-02")
    p_new.add_argument("--country", default="Россия", help="Страна/контур")
    p_new.add_argument("--topic", default="", help="Тематическая рамка")
    p_new.add_argument("--outlet", default="", help="СМИ по умолчанию")
    p_new.set_defaults(func=cmd_new_session)

    p_s1 = sub.add_parser("step1", help="Шаг 1: поиск событий")
    p_s1.add_argument("--session", required=True)
    p_s1.add_argument("--mode", choices=["manual", "api"], default="manual")
    p_s1.set_defaults(func=cmd_step1)

    p_ingest = sub.add_parser("ingest-response", help="Сохранить ответ модели")
    p_ingest.add_argument("--session", required=True)
    p_ingest.add_argument("--step", required=True, choices=sorted(VALID_STEPS))
    p_ingest.add_argument("--provider", required=True, choices=sorted(VALID_PROVIDERS))
    p_ingest.add_argument("--input-file", default=None, help="Файл с ответом (txt/md/json)")
    p_ingest.set_defaults(func=cmd_ingest_response)

    p_event = sub.add_parser("select-event", help="Выбрать событие из шага 1")
    p_event.add_argument("--session", required=True)
    p_event.add_argument("--event-id", required=True)
    p_event.set_defaults(func=cmd_select_event)

    p_s2 = sub.add_parser("step2", help="Шаг 2: тренды и сценарии")
    p_s2.add_argument("--session", required=True)
    p_s2.add_argument("--mode", choices=["manual", "api"], default="manual")
    p_s2.add_argument("--notes", default="", help="Комментарий пользователя для шага 2")
    p_s2.set_defaults(func=cmd_step2)

    p_sel_scn = sub.add_parser("select-scenario", help="Выбрать сценарий")
    p_sel_scn.add_argument("--session", required=True)
    p_sel_scn.add_argument("--scenario", required=True, choices=sorted(VALID_SCENARIOS))
    p_sel_scn.set_defaults(func=cmd_select_scenario)

    p_s3 = sub.add_parser("step3", help="Шаг 3: анализ стиля СМИ")
    p_s3.add_argument("--session", required=True)
    p_s3.add_argument("--outlet", default="", help="Название СМИ")
    p_s3.add_argument("--mode", choices=["manual", "api"], default="manual")
    p_s3.set_defaults(func=cmd_step3)

    p_s4 = sub.add_parser("step4", help="Шаг 4: генерация OpenAI/DeepSeek/Qwen")
    p_s4.add_argument("--session", required=True)
    p_s4.add_argument("--mode", choices=["manual", "api"], default="manual")
    p_s4.set_defaults(func=cmd_step4)

    p_cmp = sub.add_parser("compare", help="Сравнить ответы шагa 4")
    p_cmp.add_argument("--session", required=True)
    p_cmp.set_defaults(func=cmd_compare)

    p_status = sub.add_parser("status", help="Показать статус сессии")
    p_status.add_argument("--session", required=True)
    p_status.set_defaults(func=cmd_status)

    p_winner = sub.add_parser("select-winner", help="Выбрать финального победителя")
    p_winner.add_argument("--session", required=True)
    p_winner.add_argument("--provider", required=True, choices=sorted(VALID_PROVIDERS))
    p_winner.add_argument("--variant", required=True, choices=sorted(VALID_SCENARIOS))
    p_winner.set_defaults(func=cmd_select_winner)

    p_readme = sub.add_parser("build-readme", help="Собрать README из .docx методики")
    p_readme.add_argument("--docx", required=True)
    p_readme.add_argument("--output", default="README.md")
    p_readme.set_defaults(func=cmd_build_readme)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
