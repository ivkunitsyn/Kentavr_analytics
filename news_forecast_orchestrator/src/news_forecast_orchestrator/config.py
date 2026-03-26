from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


@dataclass(slots=True)
class ProviderSettings:
    name: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(slots=True)
class PathSettings:
    project_root: Path
    data_dir: Path
    prompts_dir: Path
    sessions_dir: Path


@dataclass(slots=True)
class AppSettings:
    default_country: str
    default_mode: str
    paths: PathSettings
    providers: dict[str, ProviderSettings]

    def provider(self, name: str) -> ProviderSettings:
        key = name.strip().lower()
        if key not in self.providers:
            raise KeyError(f"Неизвестный провайдер: {name}")
        return self.providers[key]


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _read_toml(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _pick(config: dict, env: dict[str, str], section: str, name: str, env_key: str, default: str = "") -> str:
    cfg_value = (
        config.get("providers", {})
        .get(section, {})
        .get(name)
    )
    if cfg_value is not None and str(cfg_value).strip():
        return str(cfg_value).strip()
    return env.get(env_key, default).strip()


def load_settings(config_path: str | None = None) -> AppSettings:
    project_root = Path(__file__).resolve().parents[2]

    env_file_data = _read_env_file(project_root / ".env")
    merged_env = dict(env_file_data)
    merged_env.update({k: v for k, v in os.environ.items() if isinstance(v, str)})

    config_data = _read_toml(Path(config_path) if config_path else None)

    paths_cfg = config_data.get("paths", {})
    data_dir = project_root / str(paths_cfg.get("data_dir", "data"))
    prompts_dir = project_root / str(paths_cfg.get("prompts_dir", "prompts"))

    providers = {
        "openai": ProviderSettings(
            name="openai",
            api_key=_pick(config_data, merged_env, "openai", "api_key", "OPENAI_API_KEY"),
            base_url=_pick(config_data, merged_env, "openai", "base_url", "OPENAI_BASE_URL"),
            model=_pick(config_data, merged_env, "openai", "model", "OPENAI_MODEL", "gpt-4.1"),
        ),
        "deepseek": ProviderSettings(
            name="deepseek",
            api_key=_pick(config_data, merged_env, "deepseek", "api_key", "DEEPSEEK_API_KEY"),
            base_url=_pick(config_data, merged_env, "deepseek", "base_url", "DEEPSEEK_BASE_URL"),
            model=_pick(config_data, merged_env, "deepseek", "model", "DEEPSEEK_MODEL", "deepseek-chat"),
        ),
        "qwen": ProviderSettings(
            name="qwen",
            api_key=_pick(config_data, merged_env, "qwen", "api_key", "QWEN_API_KEY"),
            base_url=_pick(config_data, merged_env, "qwen", "base_url", "QWEN_BASE_URL"),
            model=_pick(config_data, merged_env, "qwen", "model", "QWEN_MODEL", "qwen-plus"),
        ),
    }

    app_cfg = config_data.get("app", {})
    default_country = str(app_cfg.get("default_country", "Россия"))
    default_mode = str(app_cfg.get("default_mode", "manual"))

    path_settings = PathSettings(
        project_root=project_root,
        data_dir=data_dir,
        prompts_dir=prompts_dir,
        sessions_dir=data_dir / "sessions",
    )

    return AppSettings(
        default_country=default_country,
        default_mode=default_mode,
        paths=path_settings,
        providers=providers,
    )
