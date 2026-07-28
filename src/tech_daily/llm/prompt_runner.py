"""Prompt loading, LLM invocation, JSON parsing, and schema validation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

from tech_daily.llm.client import ClaudeLLMClient, TextLLMClient
from tech_daily.llm.errors import ProviderExhaustedError

__all__ = ["PromptRunner", "PromptRunnerError", "parse_json_response"]

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROMPT_ROOT = ROOT / "prompts"

T = TypeVar("T", bound=BaseModel)


@dataclass
class PromptRunnerError(Exception):
    kind: str
    message: str
    raw_response: str = ""

    def __str__(self) -> str:
        return f"{self.kind}: {self.message}"


def parse_json_response(raw_response: str) -> Any:
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


class PromptRunner:
    def __init__(
        self,
        llm_client: TextLLMClient | None = None,
        prompt_root: str | os.PathLike[str] = DEFAULT_PROMPT_ROOT,
    ):
        self.llm_client = llm_client or ClaudeLLMClient()
        self.prompt_root = Path(prompt_root)

    def load_prompt(self, prompt_path: str) -> str:
        path = self.prompt_root / prompt_path
        with open(path, encoding="utf-8") as f:
            return f.read()

    def run_json(
        self,
        *,
        prompt_path: str,
        payload: dict[str, Any] | list[Any] | str,
        schema: type[T],
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
    ) -> T:
        system = self.load_prompt(prompt_path)
        user = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        structured_generator = getattr(self.llm_client, "generate_structured", None)
        if callable(structured_generator):
            try:
                return cast(
                    T,
                    structured_generator(
                        system=system,
                        user=user,
                        schema=schema,
                        model=model,
                        max_tokens=max_tokens,
                        cache_system=cache_system,
                    ),
                )
            except ProviderExhaustedError as error:
                raise PromptRunnerError(
                    kind="provider_exhausted",
                    message=str(error),
                ) from error

        raw_response = self.llm_client.generate_text(
            system=system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            cache_system=cache_system,
            auto_continue=False,
        )
        try:
            parsed = parse_json_response(raw_response)
        except json.JSONDecodeError as e:
            raise PromptRunnerError(
                kind="json_parse_error",
                message=str(e),
                raw_response=raw_response,
            ) from e
        try:
            return schema.model_validate(parsed)
        except ValidationError as e:
            raise PromptRunnerError(
                kind="schema_validation_error",
                message=str(e),
                raw_response=raw_response,
            ) from e

    def run_text(
        self,
        *,
        prompt_path: str,
        payload: dict[str, Any] | list[Any] | str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        cache_system: bool = True,
    ) -> str:
        system = self.load_prompt(prompt_path)
        user = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return self.llm_client.generate_text(
            system=system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            cache_system=cache_system,
            auto_continue=True,
        )
