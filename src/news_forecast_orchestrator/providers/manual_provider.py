from __future__ import annotations

from .base import BaseProvider, ProviderError


class ManualProvider(BaseProvider):
    @property
    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise ProviderError(
            "ManualProvider не вызывает модель напрямую. Используйте copy/paste и `ingest-response`."
        )
