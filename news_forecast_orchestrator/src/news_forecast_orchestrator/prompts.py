from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PromptLibrary:
    prompts_dir: Path

    def _read(self, filename: str) -> str:
        path = self.prompts_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Не найден файл промпта: {path}")
        return path.read_text(encoding="utf-8")

    def step1(self) -> str:
        return self._read("step1_event_search.md")

    def step2(self) -> str:
        return self._read("step2_trend_scenarios.md")

    def step3(self) -> str:
        return self._read("step3_outlet_style.md")

    def step4(self) -> str:
        return self._read("step4_generation.md")

    def step4_comparison(self) -> str:
        return self._read("step4_comparison.md")


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_prompt(template: str, **context: str) -> str:
    safe_context = _SafeFormatDict({k: v for k, v in context.items()})
    return template.format_map(safe_context)
