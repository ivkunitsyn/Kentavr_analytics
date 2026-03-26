from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from .compare_outputs import build_comparison_markdown
from .config import AppSettings, load_settings
from .formatter import format_next_instruction, format_summary
from .parser import parse_by_step
from .prompts import PromptLibrary, render_prompt
from .providers import provider_factory
from .providers.base import ProviderError
from .readme_builder import build_readme
from .session import SessionService
from .steps.step1_event_search import prepare_step1_prompt
from .steps.step2_trend_scenarios import prepare_step2_prompt, resolve_selected_scenario
from .steps.step3_outlet_style import prepare_step3_prompt
from .steps.step4_generation import prepare_step4_prompts
from .storage import SessionStorage


VALID_STEPS = {"step1", "step2", "step3", "step4", "step5"}
VALID_PROVIDERS = {"openai", "deepseek", "qwen"}
VALID_SCENARIOS = {"base", "cautious", "stronger"}
VALID_SCENARIOS_AUTO = {"auto", *VALID_SCENARIOS}


def _bootstrap(config_path: str | None = None) -> tuple[AppSettings, SessionStorage, SessionService, PromptLibrary]:
    settings = load_settings(config_path=config_path)
    storage = SessionStorage(settings.paths.sessions_dir)
    sessions = SessionService(storage)
    prompts = PromptLibrary(settings.paths.prompts_dir)
    return settings, storage, sessions, prompts


def _slugify(text: str) -> str:
    normalized = text.strip().lower().replace("ё", "е")
    normalized = re.sub(r"[^a-zа-я0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or "outlet"


def _parse_csv_list(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _normalize_scenario_name(value: str) -> str:
    lower = value.strip().lower()
    if lower in VALID_SCENARIOS:
        return lower
    if "осторож" in lower:
        return "cautious"
    if "силь" in lower:
        return "stronger"
    if "баз" in lower:
        return "base"
    return "base"


def _choose_auto_scenario(parsed_step2: dict) -> str:
    preferred = str(parsed_step2.get("selected_scenario", "")).strip()
    if preferred:
        return _normalize_scenario_name(preferred)

    for key in ("base_scenario", "cautious_scenario", "stronger_scenario"):
        if str(parsed_step2.get(key, "")).strip():
            return {
                "base_scenario": "base",
                "cautious_scenario": "cautious",
                "stronger_scenario": "stronger",
            }[key]
    return "base"


def _load_required_json(storage: SessionStorage, session_id: str, relative_path: str, hint: str) -> dict:
    if not storage.exists(session_id, relative_path):
        raise SystemExit(f"Не найден файл `{relative_path}`. Сначала выполните: {hint}")
    return storage.read_json(session_id, relative_path)


def _read_json_if_exists(storage: SessionStorage, session_id: str, relative_path: str) -> dict | None:
    if not storage.exists(session_id, relative_path):
        return None
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
    base_dir: str | None = None,
    echo: bool = True,
) -> dict:
    step_dir = base_dir or step
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
    if step == "step4":
        summary_rel = f"{step_dir}/summary_{provider}.md"
    else:
        summary_rel = f"{step_dir}/summary.md"

    storage.write_text(manifest.session_id, summary_rel, summary_text)
    sessions.register_file(manifest, summary_rel)

    sessions.update_step(manifest, f"{step}_response_ingested")
    sessions.save_manifest(manifest)

    if echo:
        print(f"Ответ сохранён: {raw_rel}")
        print(f"Parsed сохранён: {parsed_rel}")
        print(f"Summary сохранён: {summary_rel}")
        print("\n" + summary_text)

    return parsed


def _generate_and_store_api(
    settings: AppSettings,
    storage: SessionStorage,
    sessions: SessionService,
    manifest,
    *,
    step: str,
    provider: str,
    prompt: str,
    context: dict[str, str] | None = None,
    base_dir: str | None = None,
    require_key: bool,
    echo: bool,
) -> dict | None:
    api_provider = provider_factory(provider, settings)
    if not api_provider.is_available:
        if require_key:
            raise SystemExit(f"Для автоматического шага `{step}` нужен API-ключ провайдера `{provider}`.")
        if echo:
            print(f"`{provider}` не настроен, шаг `{step}` пропущен.")
        return None

    try:
        raw_text = api_provider.generate(prompt)
    except ProviderError as exc:
        raise SystemExit(f"Ошибка API-вызова `{provider}` на шаге `{step}`: {exc}") from exc

    return _save_ingest(
        storage,
        sessions,
        manifest,
        step=step,
        provider=provider,
        raw_text=raw_text,
        context=context,
        base_dir=base_dir,
        echo=echo,
    )


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


def _load_step4_outputs(storage: SessionStorage, session_id: str, step4_dir: str = "step4") -> dict[str, dict]:
    outputs: dict[str, dict] = {}
    for provider in ("openai", "deepseek", "qwen"):
        rel = f"{step4_dir}/response_{provider}_parsed.json"
        if storage.exists(session_id, rel):
            outputs[provider] = storage.read_json(session_id, rel)
    return outputs


def _build_and_save_comparison(
    storage: SessionStorage,
    sessions: SessionService,
    manifest,
    step4_dir: str = "step4",
) -> Path:
    outputs = _load_step4_outputs(storage, manifest.session_id, step4_dir=step4_dir)
    if not outputs:
        raise SystemExit("Для сравнения нет parsed-файлов шага 4.")

    comparison = build_comparison_markdown(outputs)
    rel = f"{step4_dir}/comparison.md"
    path = storage.write_text(manifest.session_id, rel, comparison)
    sessions.register_file(manifest, rel)
    sessions.update_step(manifest, "step4_compared")
    sessions.save_manifest(manifest)
    return path


def _extract_event_payload(step1_parsed: dict, event_id: str) -> dict:
    for item in step1_parsed.get("candidates", []):
        if item.get("id") == event_id:
            return item
    return {}


def _build_step5_prompt(
    prompts: PromptLibrary,
    outlet_name: str,
    event_payload: dict,
    agenda_notes: str,
    outputs_by_provider: dict[str, dict],
) -> str:
    variants: list[dict] = []
    for provider, parsed in outputs_by_provider.items():
        for draft in parsed.get("drafts", []):
            variants.append(
                {
                    "provider": provider,
                    "variant_type": draft.get("variant_type", ""),
                    "headline": draft.get("headline", ""),
                    "lead": draft.get("lead", ""),
                    "selected_by_model": bool(draft.get("selected_by_model", False)),
                }
            )

    return render_prompt(
        prompts.step5_editorial_committee(),
        outlet_name=outlet_name,
        event_payload=json.dumps(event_payload, ensure_ascii=False, indent=2),
        agenda_notes=agenda_notes or "нет",
        variants_payload=json.dumps(variants, ensure_ascii=False, indent=2),
    )


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
    storage.write_json(manifest.session_id, "step1/selected_events.json", [args.event_id])
    sessions.register_file(manifest, "step1/selected_event.txt")
    sessions.register_file(manifest, "step1/selected_events.json")
    sessions.save_manifest(manifest)

    print(f"Выбрано событие: {args.event_id}")


def cmd_select_events(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)
    parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step1/response_openai_parsed.json",
        "step1 + ingest-response для step1",
    )

    requested = _parse_csv_list(args.event_ids)
    if not requested:
        raise SystemExit("Передайте список через --event-ids, например: event_01,event_03")

    candidates = {item.get("id", ""): item for item in parsed.get("candidates", [])}
    missing = [event_id for event_id in requested if event_id not in candidates]
    if missing:
        raise SystemExit(f"Не найдены события: {', '.join(missing)}")

    sessions.set_chosen_event(manifest, requested[0])
    storage.write_json(manifest.session_id, "step1/selected_events.json", requested)
    storage.write_text(manifest.session_id, "step1/selected_event.txt", requested[0])
    sessions.register_file(manifest, "step1/selected_events.json")
    sessions.register_file(manifest, "step1/selected_event.txt")
    sessions.update_step(manifest, "events_selected")
    sessions.save_manifest(manifest)

    print(f"Выбраны события: {', '.join(requested)}")


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


def cmd_step5(args: argparse.Namespace) -> None:
    settings, storage, sessions, prompts = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    step4_dir = f"step4/runs/{args.run_id}" if args.run_id else "step4"
    step5_dir = f"step5/runs/{args.run_id}" if args.run_id else "step5"

    outputs = _load_step4_outputs(storage, manifest.session_id, step4_dir=step4_dir)
    if not outputs:
        raise SystemExit(f"Не найдены parsed-ответы шага 4 в `{step4_dir}`.")

    input_payload = _read_json_if_exists(storage, manifest.session_id, f"{step4_dir}/input_from_step3.json") or {}
    event_payload = input_payload.get("event", {})
    if not event_payload and manifest.chosen_event:
        step1_parsed = _load_required_json(
            storage,
            manifest.session_id,
            "step1/response_openai_parsed.json",
            "step1 + ingest-response для step1",
        )
        event_payload = _extract_event_payload(step1_parsed, manifest.chosen_event)

    outlet_name = input_payload.get("outlet") or manifest.chosen_outlet or "не задано"
    agenda_notes = str(input_payload.get("scenario_text", "")).strip()

    prompt = _build_step5_prompt(
        prompts,
        outlet_name=outlet_name,
        event_payload=event_payload,
        agenda_notes=agenda_notes,
        outputs_by_provider=outputs,
    )

    prompt_rel = f"{step5_dir}/prompt_openai.txt"
    storage.write_text(manifest.session_id, prompt_rel, prompt)
    sessions.register_file(manifest, prompt_rel)
    sessions.update_step(manifest, "step5_prompt_ready")
    sessions.save_manifest(manifest)

    print(f"Prompt шага 5 сохранён: {prompt_rel}")
    if args.mode == "manual":
        print("\n=== PROMPT STEP5 (OPENAI) ===\n")
        print(prompt)
        print("\nЧто дальше:")
        print("1. Отправьте prompt в OpenAI.")
        print("2. Верните ответ через ingest-response --step step5 --provider openai.")
        return

    parsed = _generate_and_store_api(
        settings,
        storage,
        sessions,
        manifest,
        step="step5",
        provider="openai",
        prompt=prompt,
        context={
            "event_id": str(event_payload.get("id", manifest.chosen_event)),
            "outlet_name": outlet_name,
        },
        base_dir=step5_dir,
        require_key=True,
        echo=False,
    )
    if parsed is not None:
        print(f"Шаг 5 завершён. Топ-3: {', '.join(parsed.get('top3', [])) or 'не извлечены'}")


def cmd_auto_run(args: argparse.Namespace) -> None:
    settings, storage, sessions, prompts = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)

    step1_parsed = _load_required_json(
        storage,
        manifest.session_id,
        "step1/response_openai_parsed.json",
        "step1 + ingest-response для step1",
    )

    event_ids = _parse_csv_list(args.event_ids)
    if not event_ids:
        selected_events = _read_json_if_exists(storage, manifest.session_id, "step1/selected_events.json")
        if isinstance(selected_events, list) and selected_events:
            event_ids = [str(item) for item in selected_events]
    if not event_ids and manifest.chosen_event:
        event_ids = [manifest.chosen_event]
    if not event_ids:
        raise SystemExit(
            "Не выбраны события. Укажите --event-ids event_01,event_03 или выполните select-events/select-event."
        )

    outlets = _parse_csv_list(args.outlets)
    if not outlets and manifest.chosen_outlet:
        outlets = [manifest.chosen_outlet]
    if not outlets:
        raise SystemExit("Не заданы СМИ. Передайте --outlets, например: \"РБК,Коммерсантъ\".")

    valid_event_ids = {item.get("id", "") for item in step1_parsed.get("candidates", [])}
    missing = [event_id for event_id in event_ids if event_id not in valid_event_ids]
    if missing:
        raise SystemExit(f"В step1 parsed отсутствуют события: {', '.join(missing)}")

    if not settings.provider("openai").is_configured:
        raise SystemExit("Для auto-run обязателен OPENAI_API_KEY.")

    missing_generation_providers = [
        provider for provider in ("openai", "deepseek", "qwen") if not settings.provider(provider).is_configured
    ]
    if missing_generation_providers and not args.allow_missing_providers:
        raise SystemExit(
            "Для полного auto-run нужны ключи OpenAI/DeepSeek/Qwen. "
            f"Отсутствуют: {', '.join(missing_generation_providers)}. "
            "Или запустите с --allow-missing-providers."
        )

    print(f"Автопрогон: событий={len(event_ids)}, СМИ={len(outlets)}")

    runs: list[dict] = []
    for event_id in event_ids:
        manifest.chosen_event = event_id
        prompt2, event_payload = prepare_step2_prompt(
            manifest,
            prompts,
            step1_parsed,
            user_notes=args.notes or "",
        )

        step2_dir = f"step2/runs/{event_id}"
        storage.write_json(manifest.session_id, f"{step2_dir}/input_from_step1.json", event_payload or {})
        storage.write_text(manifest.session_id, f"{step2_dir}/prompt_openai.txt", prompt2)
        sessions.register_file(manifest, f"{step2_dir}/input_from_step1.json")
        sessions.register_file(manifest, f"{step2_dir}/prompt_openai.txt")

        parsed2 = _generate_and_store_api(
            settings,
            storage,
            sessions,
            manifest,
            step="step2",
            provider="openai",
            prompt=prompt2,
            context={"event_id": event_id},
            base_dir=step2_dir,
            require_key=True,
            echo=False,
        )
        if parsed2 is None:
            raise SystemExit(f"Не удалось выполнить step2 для `{event_id}`")

        scenario_name = args.scenario if args.scenario != "auto" else _choose_auto_scenario(parsed2)
        parsed2["selected_scenario"] = scenario_name
        storage.write_json(manifest.session_id, f"{step2_dir}/response_openai_parsed.json", parsed2)

        for outlet in outlets:
            manifest.chosen_outlet = outlet
            manifest.chosen_scenario = scenario_name
            run_id = f"{event_id}__{_slugify(outlet)}"
            print(f"- Обработка run `{run_id}`")

            step3_dir = f"step3/runs/{run_id}"
            prompt3, input3 = prepare_step3_prompt(manifest, prompts, step1_parsed, parsed2)
            storage.write_json(manifest.session_id, f"{step3_dir}/input_from_step2.json", input3)
            storage.write_text(manifest.session_id, f"{step3_dir}/prompt_openai.txt", prompt3)
            sessions.register_file(manifest, f"{step3_dir}/input_from_step2.json")
            sessions.register_file(manifest, f"{step3_dir}/prompt_openai.txt")

            parsed3 = _generate_and_store_api(
                settings,
                storage,
                sessions,
                manifest,
                step="step3",
                provider="openai",
                prompt=prompt3,
                context={"outlet_name": outlet},
                base_dir=step3_dir,
                require_key=True,
                echo=False,
            )
            if parsed3 is None:
                raise SystemExit(f"Не удалось выполнить step3 для `{run_id}`")

            step4_dir = f"step4/runs/{run_id}"
            prompts_by_provider, input4 = prepare_step4_prompts(
                manifest,
                prompts,
                step1_parsed,
                parsed2,
                parsed3,
            )
            storage.write_json(manifest.session_id, f"{step4_dir}/input_from_step3.json", input4)
            sessions.register_file(manifest, f"{step4_dir}/input_from_step3.json")
            for provider_name, provider_prompt in prompts_by_provider.items():
                rel = f"{step4_dir}/prompt_{provider_name}.txt"
                storage.write_text(manifest.session_id, rel, provider_prompt)
                sessions.register_file(manifest, rel)

            outputs: dict[str, dict] = {}
            for provider_name in ("openai", "deepseek", "qwen"):
                parsed4 = _generate_and_store_api(
                    settings,
                    storage,
                    sessions,
                    manifest,
                    step="step4",
                    provider=provider_name,
                    prompt=prompts_by_provider[provider_name],
                    context={
                        "event_id": event_id,
                        "outlet_name": outlet,
                        "scenario_type": scenario_name,
                    },
                    base_dir=step4_dir,
                    require_key=not args.allow_missing_providers,
                    echo=False,
                )
                if parsed4 is not None:
                    outputs[provider_name] = parsed4

            if not outputs:
                raise SystemExit(f"Не удалось получить ни одного ответа на step4 для `{run_id}`")

            comparison = build_comparison_markdown(outputs)
            comparison_rel = f"{step4_dir}/comparison.md"
            storage.write_text(manifest.session_id, comparison_rel, comparison)
            sessions.register_file(manifest, comparison_rel)

            step5_dir = f"step5/runs/{run_id}"
            prompt5 = _build_step5_prompt(
                prompts,
                outlet_name=outlet,
                event_payload=_extract_event_payload(step1_parsed, event_id),
                agenda_notes=str(parsed2.get("current_context", "")).strip(),
                outputs_by_provider=outputs,
            )
            prompt5_rel = f"{step5_dir}/prompt_openai.txt"
            storage.write_text(manifest.session_id, prompt5_rel, prompt5)
            sessions.register_file(manifest, prompt5_rel)

            parsed5 = _generate_and_store_api(
                settings,
                storage,
                sessions,
                manifest,
                step="step5",
                provider="openai",
                prompt=prompt5,
                context={"event_id": event_id, "outlet_name": outlet},
                base_dir=step5_dir,
                require_key=True,
                echo=False,
            )

            runs.append(
                {
                    "run_id": run_id,
                    "event_id": event_id,
                    "outlet": outlet,
                    "scenario": scenario_name,
                    "providers_used": sorted(outputs.keys()),
                    "step4_comparison": comparison_rel,
                    "step5_summary": f"{step5_dir}/summary.md",
                    "step5_top3": (parsed5 or {}).get("top3", []),
                }
            )

    report_rel = "exports/auto_run_report.md"
    report_lines = [
        "# Отчёт автоматического прогона",
        "",
        f"- Сессия: {manifest.session_id}",
        f"- Дата: {manifest.target_date}",
        f"- События: {', '.join(event_ids)}",
        f"- СМИ: {', '.join(outlets)}",
        "",
        "## Результаты по run",
    ]
    for run in runs:
        report_lines.extend(
            [
                "",
                f"### {run['run_id']}",
                f"- Событие: {run['event_id']}",
                f"- СМИ: {run['outlet']}",
                f"- Сценарий: {run['scenario']}",
                f"- Модели: {', '.join(run['providers_used'])}",
                f"- Сравнение step4: {run['step4_comparison']}",
                f"- Summary step5: {run['step5_summary']}",
                f"- Топ-3 комиссии: {', '.join(run['step5_top3']) or 'не извлечены'}",
            ]
        )

    storage.write_text(manifest.session_id, report_rel, "\n".join(report_lines))
    sessions.register_file(manifest, report_rel)

    sessions.update_step(manifest, "auto_run_completed")
    sessions.save_manifest(manifest)

    print(f"Автопрогон завершён. Отчёт: {report_rel}")


def cmd_compare(args: argparse.Namespace) -> None:
    _, storage, sessions, _ = _bootstrap(args.config)
    manifest = sessions.load_manifest(args.session)
    step4_dir = f"step4/runs/{args.run_id}" if args.run_id else "step4"
    path = _build_and_save_comparison(storage, sessions, manifest, step4_dir=step4_dir)
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
    if args.step == "step5" and provider != "openai":
        raise SystemExit("Для шага 5 разрешён только provider=openai.")

    raw_text = _read_user_response(args.input_file)
    if not raw_text.strip():
        raise SystemExit("Пустой ввод. Нечего сохранять.")

    context = {
        "outlet_name": manifest.chosen_outlet,
        "event_id": manifest.chosen_event,
        "scenario_type": manifest.chosen_scenario or "base",
    }

    base_dir = args.base_dir or args.step
    _save_ingest(
        storage,
        sessions,
        manifest,
        step=args.step,
        provider=provider,
        raw_text=raw_text,
        context=context,
        base_dir=base_dir,
    )

    if args.step == "step4":
        outputs = _load_step4_outputs(storage, manifest.session_id, step4_dir=base_dir)
        if len(outputs) >= 2:
            path = _build_and_save_comparison(storage, sessions, manifest, step4_dir=base_dir)
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
        "step5/response_openai_parsed.json",
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

    step4_dir = f"step4/runs/{args.run_id}" if args.run_id else "step4"
    parsed = _load_required_json(
        storage,
        manifest.session_id,
        f"{step4_dir}/response_{provider}_parsed.json",
        f"step4 + ingest-response для нужного провайдера ({step4_dir})",
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
        f"- Run ID: {args.run_id or 'default'}",
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

    p_events = sub.add_parser("select-events", help="Выбрать несколько событий из шага 1")
    p_events.add_argument("--session", required=True)
    p_events.add_argument("--event-ids", required=True, help="Список через запятую, например event_01,event_03")
    p_events.set_defaults(func=cmd_select_events)

    p_ingest = sub.add_parser("ingest-response", help="Сохранить ответ модели")
    p_ingest.add_argument("--session", required=True)
    p_ingest.add_argument("--step", required=True, choices=sorted(VALID_STEPS))
    p_ingest.add_argument("--provider", required=True, choices=sorted(VALID_PROVIDERS))
    p_ingest.add_argument("--input-file", default=None, help="Файл с ответом (txt/md/json)")
    p_ingest.add_argument(
        "--base-dir",
        default=None,
        help="Кастомная папка шага внутри сессии, например step4/runs/event_01__rbk",
    )
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

    p_s5 = sub.add_parser("step5", help="Шаг 5: внутренняя редакционная комиссия (OpenAI)")
    p_s5.add_argument("--session", required=True)
    p_s5.add_argument("--mode", choices=["manual", "api"], default="api")
    p_s5.add_argument(
        "--run-id",
        default="",
        help="ID прогона из auto-run, например event_01__rbk. Если не задан, используется стандартный step4/step5.",
    )
    p_s5.set_defaults(func=cmd_step5)

    p_auto = sub.add_parser(
        "auto-run",
        help="Автопрогон после выбора событий/СМИ: step2 -> step3 -> step4 -> step5",
    )
    p_auto.add_argument("--session", required=True)
    p_auto.add_argument("--event-ids", default="", help="Список событий через запятую")
    p_auto.add_argument("--outlets", default="", help="Список СМИ через запятую")
    p_auto.add_argument("--notes", default="", help="Комментарий для step2")
    p_auto.add_argument("--scenario", choices=sorted(VALID_SCENARIOS_AUTO), default="auto")
    p_auto.add_argument(
        "--allow-missing-providers",
        action="store_true",
        help="Разрешить запуск step4 без одного или двух провайдеров (по умолчанию требуются все три).",
    )
    p_auto.set_defaults(func=cmd_auto_run)

    p_cmp = sub.add_parser("compare", help="Сравнить ответы шагa 4")
    p_cmp.add_argument("--session", required=True)
    p_cmp.add_argument(
        "--run-id",
        default="",
        help="ID прогона из auto-run. Если не задан, используется стандартная папка step4.",
    )
    p_cmp.set_defaults(func=cmd_compare)

    p_status = sub.add_parser("status", help="Показать статус сессии")
    p_status.add_argument("--session", required=True)
    p_status.set_defaults(func=cmd_status)

    p_winner = sub.add_parser("select-winner", help="Выбрать финального победителя")
    p_winner.add_argument("--session", required=True)
    p_winner.add_argument("--provider", required=True, choices=sorted(VALID_PROVIDERS))
    p_winner.add_argument("--variant", required=True, choices=sorted(VALID_SCENARIOS))
    p_winner.add_argument(
        "--run-id",
        default="",
        help="ID прогона из auto-run. Если не задан, используется стандартная папка step4.",
    )
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
