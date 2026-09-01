"""Provider-neutral structured-output adapter used by optional EPUB audits.

This module does not classify EPUB content and is not part of extraction. It
only transports an explicitly requested audit to an OpenAI-compatible local or
remote endpoint, validates the JSON envelope, and caches verified responses.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Base error for an explicitly configured audit backend."""


class LLMUnavailableError(LLMError):
    """Raised when the configured endpoint cannot be reached."""


class InvalidLLMResponseError(LLMError):
    """Raised when the endpoint does not return the required JSON object."""


@dataclass(frozen=True)
class StructuredResponse:
    data: dict
    model: str
    cached: bool = False
    cache_key: str | None = None
    network_attempts: int = 0
    invalid_json_responses: int = 0


@runtime_checkable
class StructuredLLMBackend(Protocol):
    """Minimal backend contract consumed by :func:`segnatura.audit`."""

    def request_structured(self, input_data: dict, system_prompt: str,
                           schema: dict, prompt_version: str) \
            -> StructuredResponse: ...


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    """Configuration for a Chat Completions compatible endpoint."""

    model: str
    base_url: str
    api_key: str | None = None
    timeout: float = 180.0
    temperature: float = 0.0
    max_tokens: int = 320
    reasoning_effort: str | None = None
    cache: Path | str | None = Path(".segnatura-cache") / "llm"
    discover_model: bool = False

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if not self.base_url.strip():
            raise ValueError("base_url cannot be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be positive")


Transport = Callable[[str, str, dict | None, dict[str, str], float], dict]


def _json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text,
                      flags=re.I | re.S).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidLLMResponseError(f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise InvalidLLMResponseError("the response is not a JSON object")
    return value


def _http_transport(method: str, url: str, payload: dict | None,
                    headers: dict[str, str], timeout: float) -> dict:
    body = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None else None)
    request = urllib.request.Request(
        url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:600]
        raise LLMError(
            f"LLM endpoint HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise LLMUnavailableError(
            f"LLM endpoint is not reachable at {url}: {error}") from error
    except json.JSONDecodeError as error:
        raise InvalidLLMResponseError(
            "the LLM endpoint returned invalid HTTP JSON") from error


class OpenAICompatibleBackend:
    """Structured-output backend for compatible local or remote endpoints.

    A remote endpoint receives excerpts from the EPUB. Supplying such an
    endpoint is therefore an explicit caller-controlled privacy decision.
    """

    def __init__(self, config: OpenAICompatibleConfig,
                 transport: Transport | None = None):
        self.config = config
        self._transport = transport or _http_transport
        self._resolved_model: str | None = None

    @classmethod
    def lm_studio(cls, model: str, *,
                  base_url: str = "http://localhost:1234/v1",
                  api_key: str = "lm-studio", **kwargs):
        return cls(OpenAICompatibleConfig(
            model=model,
            base_url=base_url,
            api_key=api_key,
            discover_model=True,
            **kwargs,
        ))

    @property
    def base_url(self) -> str:
        return self.config.base_url.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return self._headers(self.config.api_key)

    @staticmethod
    def _headers(api_key: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @classmethod
    def discover_models(
            cls, *, base_url: str, api_key: str | None = None,
            timeout: float = 180.0, transport: Transport | None = None,
    ) -> list[str]:
        """List models without constructing a model-specific backend."""
        if not base_url.strip():
            raise ValueError("base_url cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        request = transport or _http_transport
        response = request(
            "GET", f"{base_url.rstrip('/')}/models", None,
            cls._headers(api_key), timeout)
        return [str(item["id"]) for item in response.get("data", [])
                if isinstance(item, dict) and item.get("id")]

    def list_models(self) -> list[str]:
        """Return model identifiers exposed by the compatible endpoint."""
        return self.discover_models(
            base_url=self.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
            transport=self._transport,
        )

    def _resolve_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model
        requested = self.config.model.strip()
        if not self.config.discover_model:
            return requested
        available = self.list_models()
        if requested in available:
            self._resolved_model = requested
            return requested
        words = re.findall(r"[a-z0-9]+", requested.casefold())
        candidates = [model for model in available
                      if all(word in model.casefold() for word in words)]
        if len(candidates) == 1:
            self._resolved_model = candidates[0]
            return candidates[0]
        if not candidates:
            listing = ", ".join(available) or "no models exposed"
            raise LLMError(
                f"model {requested!r} was not found; available: {listing}")
        raise LLMError(
            f"{requested!r} matches multiple models: {', '.join(candidates)}")

    def _cache_key(self, model: str, input_data: dict,
                   prompt_version: str, schema: dict) -> str:
        material = json.dumps({
            "protocol": "chat-completions-json-schema-v1",
            "base_url": self.base_url.casefold(),
            "model": model,
            "prompt_version": prompt_version,
            "schema": schema,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "reasoning_effort": self.config.reasoning_effort,
            "input": input_data,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _cache_file(self, key: str) -> Path | None:
        if self.config.cache is None:
            return None
        return Path(self.config.cache) / key[:2] / f"{key}.json"

    @staticmethod
    def _load_cache(path: Path | None) -> dict | None:
        if not path or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _save_cache(path: Path | None, data: dict) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def request_structured(self, input_data: dict, system_prompt: str,
                           schema: dict, prompt_version: str, *,
                           retry_invalid: bool = True) \
            -> StructuredResponse:
        model = self._resolve_model()
        key = self._cache_key(model, input_data, prompt_version, schema)
        cache_file = self._cache_file(key)
        cached = self._load_cache(cache_file)
        if cached is not None:
            return StructuredResponse(
                data=cached["response"], model=model, cached=True,
                cache_key=key)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(
                input_data, ensure_ascii=False, separators=(",", ":"))},
        ]
        base_payload = {
            "model": model,
            "messages": messages,
            "response_format": schema,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }
        if self.config.reasoning_effort is not None:
            base_payload["reasoning_effort"] = self.config.reasoning_effort

        invalid_count = 0
        data = None
        for attempt in range(2 if retry_invalid else 1):
            payload = dict(base_payload)
            payload["messages"] = list(messages)
            if attempt:
                payload["max_tokens"] = min(
                    8192, max(4800, self.config.max_tokens * 2))
                payload["messages"][0] = {
                    "role": "system",
                    "content": system_prompt +
                    "\nThe previous generation was not valid JSON. Return "
                    "one concise and complete JSON object only.",
                }
            response = self._transport(
                "POST", f"{self.base_url}/chat/completions", payload,
                self.headers, self.config.timeout)
            try:
                content = response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as error:
                raise InvalidLLMResponseError(
                    "LLM response is missing choices[0].message.content"
                ) from error
            try:
                data = _json_object(content)
                break
            except InvalidLLMResponseError as error:
                invalid_count += 1
                diagnostic = None
                if cache_file:
                    diagnostic = cache_file.with_name(
                        f"{key}.invalid-{attempt + 1}.json")
                    self._save_cache(diagnostic, {
                        "prompt_version": prompt_version,
                        "model": model,
                        "cache_key": key,
                        "attempt": attempt + 1,
                        "finish_reason": response.get("choices", [{}])[0].get(
                            "finish_reason"),
                        "content": content,
                    })
                if attempt:
                    suffix = (f"; diagnostics: {diagnostic}"
                              if diagnostic else "")
                    raise InvalidLLMResponseError(
                        f"invalid JSON after one retry: {error}{suffix}"
                    ) from error
        if data is None:
            raise InvalidLLMResponseError(
                "structured response missing after all retry attempts")
        self._save_cache(cache_file, {
            "prompt_version": prompt_version,
            "model": model,
            "cache_key": key,
            "network_attempts": 1 + invalid_count,
            "invalid_json_responses": invalid_count,
            "response": data,
        })
        return StructuredResponse(
            data=data,
            model=model,
            cached=False,
            cache_key=key,
            network_attempts=1 + invalid_count,
            invalid_json_responses=invalid_count,
        )


__all__ = [
    "LLMError", "LLMUnavailableError", "InvalidLLMResponseError",
    "StructuredResponse", "StructuredLLMBackend",
    "OpenAICompatibleConfig", "OpenAICompatibleBackend",
]
