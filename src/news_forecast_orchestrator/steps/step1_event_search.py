from __future__ import annotations

from ..models import SessionManifest
from ..prompts import PromptLibrary, render_prompt


def prepare_step1_prompt(manifest: SessionManifest, prompts: PromptLibrary) -> str:
    theme = manifest.topic.strip() or "не задана (ищи релевантные экономические и регуляторные поводы)"
    return render_prompt(
        prompts.step1(),
        target_date=manifest.target_date,
        country=manifest.country,
        theme_or_default=theme,
    )
