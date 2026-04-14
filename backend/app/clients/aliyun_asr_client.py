from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.core.config import Settings
from app.schemas.transcript import TranscriptSegment

logger = logging.getLogger(__name__)


class AliyunTokenProvider(Protocol):
    async def get_token(self) -> str:
        """Return the token used by the ASR gateway."""


class StaticAccessKeyTokenProvider:
    def __init__(self, access_key_id: str) -> None:
        self._access_key_id = access_key_id

    async def get_token(self) -> str:
        if not self._access_key_id:
            raise RuntimeError("ALIYUN_ACCESS_KEY_ID is not configured.")
        return self._access_key_id


class AliyunASRClient:
    def __init__(
        self,
        settings: Settings,
        token_provider: AliyunTokenProvider | None = None,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider or StaticAccessKeyTokenProvider(
            settings.aliyun_access_key_id
        )
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def is_configured(self) -> bool:
        return self._settings.asr_configured

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        if not audio_data:
            return []
        if not self.is_configured:
            raise RuntimeError("Aliyun ASR credentials are not configured.")

        token = await self._token_provider.get_token()
        url = f"{self._settings.aliyun_asr_url}?appkey={self._settings.aliyun_asr_app_key}&format=wav"

        response = await self._client.post(
            url,
            content=audio_data,
            headers={
                "Content-Type": "application/octet-stream",
                "X-NLS-Token": token,
            },
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Aliyun ASR request failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        return self._parse_segments(payload)

    def _parse_segments(self, payload: dict) -> list[TranscriptSegment]:
        sentences = payload.get("flash_result", {}).get("sentences", [])
        segments: list[TranscriptSegment] = []
        for sentence in sentences:
            text = str(sentence.get("text", "")).strip()
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    text=text,
                    start=float(sentence.get("begin_time", 0)) / 1000.0,
                    end=float(sentence.get("end_time", 0)) / 1000.0,
                )
            )
        logger.info("Aliyun ASR returned %s transcript segments", len(segments))
        return segments
