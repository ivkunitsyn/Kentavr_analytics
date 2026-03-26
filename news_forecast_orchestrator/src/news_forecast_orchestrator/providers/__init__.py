from __future__ import annotations

from ..config import AppSettings
from .base import BaseProvider
from .deepseek_provider import DeepSeekProvider
from .manual_provider import ManualProvider
from .openai_provider import OpenAIProvider
from .qwen_provider import QwenProvider


def provider_factory(name: str, settings: AppSettings, force_manual: bool = False) -> BaseProvider:
    key = name.lower().strip()
    if force_manual:
        return ManualProvider(settings.provider(key))

    if key == "openai":
        return OpenAIProvider(settings.provider("openai"))
    if key == "deepseek":
        return DeepSeekProvider(settings.provider("deepseek"))
    if key == "qwen":
        return QwenProvider(settings.provider("qwen"))

    raise ValueError(f"Неизвестный провайдер: {name}")
