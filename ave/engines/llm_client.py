from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from ave.config import LLMConfig
from ave.exceptions import LLMResponseError, LLMUnavailableError
from ave.utils.logging import get_logger

logger = get_logger("llm_client")


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _clean_json_text(text: str) -> str:
    cleaned = text.lstrip("\ufeff").strip()
    cleaned = _strip_code_fences(cleaned)
    return cleaned


class LLMClient(ABC):
    def __init__(self, provider: str, model: str, config: LLMConfig) -> None:
        self.provider = provider
        self.model = model
        self.config = config

    @abstractmethod
    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        raise NotImplementedError

    def complete_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
    ) -> dict:
        json_prompt = f"{prompt}\n\nRespond ONLY with valid JSON."
        last_response = ""

        for attempt in range(max_retries + 1):
            try:
                response_text = self.complete(json_prompt, system_prompt=system_prompt)
                last_response = response_text
                cleaned = _clean_json_text(response_text)
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                if attempt >= max_retries:
                    raise LLMResponseError(
                        "LLM response is not valid JSON",
                        raw_response=last_response,
                        cause=exc,
                    ) from exc
                json_prompt = (
                    "You must respond with ONLY valid JSON, no other text:\n" + prompt
                )

        raise LLMResponseError("LLM response is not valid JSON", raw_response=last_response)

    @abstractmethod
    def health_check(self) -> bool:
        raise NotImplementedError


class OllamaClient(LLMClient):
    def __init__(
        self,
        model: str,
        config: LLMConfig,
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ) -> None:
        env_url = os.environ.get("AVE_OLLAMA_URL")
        self.base_url = env_url or base_url
        self.timeout = timeout
        super().__init__(provider="ollama", model=model, config=config)

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("Ollama request failed", provider="ollama", cause=exc) from exc

        content = data.get("response")
        if not isinstance(content, str):
            raise LLMResponseError("Ollama response missing content", raw_response=str(data))
        return content

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("Ollama health check failed", provider="ollama", cause=exc) from exc


class GroqClient(LLMClient):
    def __init__(
        self,
        model: str,
        config: LLMConfig,
        api_key: Optional[str] = None,
        base_url: str = "https://api.groq.com/openai/v1/chat/completions",
    ) -> None:
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise LLMUnavailableError("GROQ_API_KEY not set", provider="groq")
        self.api_key = key
        self.base_url = base_url
        super().__init__(provider="groq", model=model, config=config)

    def _build_messages(
        self, prompt: str, system_prompt: Optional[str]
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _chat_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": self.config.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.post(self.base_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("Groq request failed", provider="groq", cause=exc) from exc

        if response.status_code == 429:
            raise LLMUnavailableError(
                "Groq rate limit exceeded (HTTP 429)", provider="groq"
            )

        if response.status_code >= 400:
            raise LLMUnavailableError(
                f"Groq API error: {response.status_code}", provider="groq"
            )

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Groq response missing content", raw_response=str(data)) from exc

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return self._chat_complete(prompt, system_prompt=system_prompt)

    def health_check(self) -> bool:
        try:
            _ = self._chat_complete("ping", max_tokens=1)
            return True
        except LLMUnavailableError:
            return False


class MistralClient(LLMClient):
    def __init__(
        self,
        model: str,
        config: LLMConfig,
        api_key: Optional[str] = None,
        base_url: str = "https://api.mistral.ai/v1/chat/completions",
    ) -> None:
        key = api_key or os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise LLMUnavailableError("MISTRAL_API_KEY not set", provider="mistral")
        self.api_key = key
        self.base_url = base_url
        super().__init__(provider="mistral", model=model, config=config)

    def _build_messages(
        self, prompt: str, system_prompt: Optional[str]
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _chat_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": self.config.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.post(self.base_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("Mistral request failed", provider="mistral", cause=exc) from exc

        if response.status_code == 503:
            raise LLMUnavailableError(
                "Mistral service unavailable (HTTP 503)", provider="mistral"
            )

        if response.status_code >= 400:
            raise LLMUnavailableError(
                f"Mistral API error: {response.status_code}", provider="mistral"
            )

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Mistral response missing content", raw_response=str(data)) from exc

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return self._chat_complete(prompt, system_prompt=system_prompt)

    def health_check(self) -> bool:
        try:
            _ = self._chat_complete("ping", max_tokens=1)
            return True
        except LLMUnavailableError:
            return False


class LLMRouter:
    def __init__(self, primary: str, config: LLMConfig) -> None:
        self.primary = primary
        self.config = config
        self._order = ["ollama", "groq", "mistral"]

    def _build_chain(self) -> List[str]:
        if self.primary == "none":
            return []
        if self.primary not in self._order:
            return []
        start = self._order.index(self.primary)
        return self._order[start:]

    def _create_client(self, provider: str) -> Optional[LLMClient]:
        if provider == "ollama":
            return OllamaClient(self.config.model, config=self.config, timeout=self.config.timeout_seconds)
        if provider == "groq":
            return GroqClient(self.config.model, config=self.config)
        if provider == "mistral":
            return MistralClient(self.config.model, config=self.config)
        return None

    def get_client(self) -> Optional[LLMClient]:
        for provider in self._build_chain():
            try:
                client = self._create_client(provider)
                if client is None:
                    continue
                if client.health_check():
                    logger.debug("LLM provider selected: %s", provider)
                    return client
            except LLMUnavailableError as exc:
                logger.debug("LLM provider unavailable: %s", exc)
                continue
        return None

    def complete_with_fallback(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> Optional[str]:
        for provider in self._build_chain():
            try:
                client = self._create_client(provider)
                if client is None:
                    continue
                if not client.health_check():
                    continue
                logger.debug("LLM provider used: %s", provider)
                return client.complete(prompt, system_prompt=system_prompt)
            except LLMUnavailableError as exc:
                logger.debug("LLM provider failed: %s", exc)
                continue
        return None
