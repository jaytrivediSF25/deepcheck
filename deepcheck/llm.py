"""Thin wrapper over the Anthropic SDK.

Handles the three things every call in this project needs and none of them
should re-implement: ``pause_turn`` resumption for server-side tools, refusal
detection, and JSON extraction for structured-output calls.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import anthropic

from .config import Config

# Dynamic filtering variant — Claude Opus 5 / 4.8 / 4.7 / 4.6, Sonnet 5 / 4.6.
# Claude writes code to filter results before they hit the context window.
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"

# Enables `fallbacks="default"`: on a policy refusal the API re-runs the request
# on Anthropic's recommended fallback model rather than handing us the refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

MAX_PAUSE_RESUMES = 4


class LLMRefusal(RuntimeError):
    """The model (and any fallback) declined the request."""

    def __init__(self, category: Optional[str], explanation: str = ""):
        self.category = category
        self.explanation = explanation
        super().__init__(
            f"Request refused (category={category or 'unspecified'}). {explanation}".strip()
        )


class Client:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        # A bare constructor is correct: the SDK resolves ANTHROPIC_API_KEY,
        # ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile on its own.
        kwargs: Dict[str, Any] = {}
        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key
        self._client = anthropic.Anthropic(**kwargs)

    # ------------------------------------------------------------------
    # Core call
    # ------------------------------------------------------------------

    def call(
        self,
        *,
        system: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 16000,
        effort: str = "high",
        tools: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> anthropic.types.Message:
        """One request, with pause_turn resumption and refusal checking."""
        params: Dict[str, Any] = {
            "model": self.cfg.model,
            "max_tokens": max_tokens,
            "system": system,
            "output_config": {"effort": effort},
            "messages": list(messages),
        }
        if tools:
            params["tools"] = tools
        if output_schema:
            params["output_config"]["format"] = {
                "type": "json_schema",
                "schema": output_schema,
            }

        betas: List[str] = []
        if self.cfg.use_fallbacks:
            betas.append(FALLBACK_BETA)
            params["fallbacks"] = "default"

        response = self._create(params, betas)

        # Server-side tools run a bounded loop; `pause_turn` means "resume me".
        resumes = 0
        while response.stop_reason == "pause_turn" and resumes < MAX_PAUSE_RESUMES:
            resumes += 1
            params["messages"] = list(messages) + [
                {"role": "assistant", "content": response.content}
            ]
            response = self._create(params, betas)

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMRefusal(
                getattr(details, "category", None),
                getattr(details, "explanation", "") or "",
            )

        return response

    def _create(self, params: Dict[str, Any], betas: List[str]):
        if betas:
            return self._client.beta.messages.create(betas=betas, **params)
        return self._client.messages.create(**params)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def text_of(response) -> str:
        return "\n".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

    @staticmethod
    def search_sources(response) -> List[Dict[str, str]]:
        """Pull (title, url) out of web_search_tool_result blocks.

        On success ``.content`` is a list of results; on failure it is a single
        error object with an ``error_code`` — hence the isinstance guard.
        """
        found: List[Dict[str, str]] = []
        seen = set()
        for block in response.content:
            if block.type != "web_search_tool_result":
                continue
            content = block.content
            if not isinstance(content, list):
                continue  # error object, not results
            for result in content:
                url = getattr(result, "url", None)
                if not url or url in seen:
                    continue
                seen.add(url)
                found.append({"title": getattr(result, "title", "") or url, "url": url})
        return found

    def json_call(self, *, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """A call constrained to a JSON schema, returned parsed."""
        response = self.call(output_schema=schema, **kwargs)
        text = self.text_of(response)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            snippet = text[:300].replace("\n", " ")
            raise RuntimeError(
                f"Model did not return valid JSON (stop_reason="
                f"{response.stop_reason}): {snippet}"
            ) from exc


def web_search_tool(max_uses: int) -> Dict[str, Any]:
    return {
        "type": WEB_SEARCH_TOOL_TYPE,
        "name": "web_search",
        "max_uses": max_uses,
    }
