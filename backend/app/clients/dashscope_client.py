from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class DashScopeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=60.0)

    @property
    def is_configured(self) -> bool:
        return self._settings.llm_configured

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_chat_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured.")

        try:
            response = await self._client.post(
                self._settings.dashscope_chat_url,
                headers={
                    "Authorization": f"Bearer {self._settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.dashscope_model,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"DashScope request failed: {str(exc).strip() or exc.__class__.__name__}"
            ) from exc
        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope request failed with status {response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"DashScope returned non-JSON response: {response.text.strip() or '<empty response>'}"
            ) from exc
        choices = payload.get("choices", [])
        if not choices:
            raise RuntimeError("DashScope returned no choices.")

        content = choices[0].get("message", {}).get("content", "")
        return self._flatten_content(content)

    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured.")
        if not text.strip():
            return ""

        try:
            response = await self._client.post(
                self._settings.dashscope_chat_url,
                headers={
                    "Authorization": f"Bearer {self._settings.dashscope_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.dashscope_translation_model,
                    "messages": [{"role": "user", "content": text}],
                    "translation_options": {
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                    },
                },
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"DashScope translation request failed: {str(exc).strip() or exc.__class__.__name__}"
            ) from exc
        if response.status_code != 200:
            raise RuntimeError(
                "DashScope translation request failed with status "
                f"{response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "DashScope translation returned non-JSON response: "
                f"{response.text.strip() or '<empty response>'}"
            ) from exc
        choices = payload.get("choices", [])
        if not choices:
            raise RuntimeError("DashScope translation returned no choices.")

        content = choices[0].get("message", {}).get("content", "")
        return self._flatten_content(content).strip()

    def _flatten_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        logger.warning("DashScope returned unsupported content payload: %r", content)
        return ""
