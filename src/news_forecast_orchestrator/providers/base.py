from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import ProviderSettings


class ProviderError(RuntimeError):
    """Ошибка работы провайдера."""


class BaseProvider(ABC):
    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    @property
    def name(self) -> str:
        return self.settings.name

    @property
    def is_available(self) -> bool:
        return bool(self.settings.api_key)

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(BaseProvider):
    def _build_client(self):
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise ProviderError("Пакет `openai` не установлен. Установите зависимости из requirements.txt.") from exc

        if not self.settings.api_key:
            raise ProviderError(f"Не задан API-ключ для провайдера {self.name}.")

        kwargs = {"api_key": self.settings.api_key}
        if self.settings.base_url:
            kwargs["base_url"] = self.settings.base_url
        return OpenAI(**kwargs)

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        client = self._build_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            completion = client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                temperature=0.2,
            )
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Ошибка запроса к провайдеру {self.name}: {exc}") from exc

        content = completion.choices[0].message.content if completion.choices else ""
        if not content:
            raise ProviderError(f"Провайдер {self.name} вернул пустой ответ.")
        return content
