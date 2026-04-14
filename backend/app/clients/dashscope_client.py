from __future__ import annotations

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
        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope request failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        choices = payload.get("choices", [])
        if not choices:
            raise RuntimeError("DashScope returned no choices.")

        content = choices[0].get("message", {}).get("content", "")
        return self._flatten_content(content)

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
