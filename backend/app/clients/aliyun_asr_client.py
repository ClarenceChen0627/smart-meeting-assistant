from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import quote
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.schemas.transcript import TranscriptSegment

logger = logging.getLogger(__name__)


def _percent_encode(value: str) -> str:
    return quote(str(value), safe="~")


def _format_http_error(exc: httpx.HTTPError) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    request = getattr(exc, "request", None)
    if request is not None:
        return f"{message} ({request.method} {request.url})"
    return message


class AliyunTokenProvider(Protocol):
    async def get_token(self) -> str:
        """Return the token used by the ASR gateway."""


class StaticNLSTokenProvider:
    def __init__(self, token: str) -> None:
        self._token = token.strip()

    async def get_token(self) -> str:
        if not self._token:
            raise RuntimeError("ALIYUN_NLS_TOKEN is not configured.")
        return self._token


class AliyunCreateTokenProvider:
    def __init__(
        self,
        *,
        settings: Settings,
        client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._client = client
        self._cached_token: str = ""
        self._expires_at: int = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        if self._token_is_valid():
            return self._cached_token

        async with self._lock:
            if self._token_is_valid():
                return self._cached_token

            token, expires_at = await self._create_token()
            self._cached_token = token
            self._expires_at = expires_at
            logger.info("Fetched Aliyun NLS token valid until %s", expires_at)
            return token

    def _token_is_valid(self) -> bool:
        return bool(self._cached_token and (self._expires_at - 60) > int(time.time()))

    async def _create_token(self) -> tuple[str, int]:
        if not self._settings.aliyun_access_key_id or not self._settings.aliyun_access_key_secret:
            raise RuntimeError(
                "Aliyun ASR credentials are incomplete. Configure ALIYUN_ACCESS_KEY_ID and "
                "ALIYUN_ACCESS_KEY_SECRET, or provide ALIYUN_NLS_TOKEN."
            )

        params = {
            "AccessKeyId": self._settings.aliyun_access_key_id,
            "Action": "CreateToken",
            "Format": "JSON",
            "RegionId": self._settings.aliyun_region_id,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": uuid4().hex,
            "SignatureVersion": "1.0",
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2019-02-28",
        }
        params["Signature"] = self._sign(params)

        try:
            response = await self._client.post(self._settings.aliyun_token_url, params=params)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Aliyun token request failed: {_format_http_error(exc)}") from exc

        if response.status_code != 200:
            raise RuntimeError(
                "Aliyun token request failed with status "
                f"{response.status_code}: {response.text.strip() or '<empty response>'}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Aliyun token endpoint returned non-JSON response: "
                f"{response.text.strip() or '<empty response>'}"
            ) from exc

        token_payload = payload.get("Token") or {}
        token = str(token_payload.get("Id", "")).strip()
        expire_time = token_payload.get("ExpireTime")
        if not token:
            error_code = payload.get("Code") or "UnknownTokenError"
            error_message = payload.get("Message") or payload.get("ErrMsg") or response.text
            raise RuntimeError(
                f"Aliyun token request failed: {error_code}: "
                f"{str(error_message).strip() or '<empty response>'}"
            )

        try:
            expires_at = int(expire_time)
        except (TypeError, ValueError):
            expires_at = int(time.time()) + 300

        return token, expires_at

    def _sign(self, params: dict[str, str]) -> str:
        sorted_params = sorted(params.items(), key=lambda item: item[0])
        canonicalized_query = "&".join(
            f"{_percent_encode(key)}={_percent_encode(value)}"
            for key, value in sorted_params
        )
        string_to_sign = f"POST&{_percent_encode('/')}&{_percent_encode(canonicalized_query)}"
        digest = hmac.new(
            f"{self._settings.aliyun_access_key_secret}&".encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")


class AliyunASRClient:
    def __init__(
        self,
        settings: Settings,
        token_provider: AliyunTokenProvider | None = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self._token_provider = token_provider or self._build_token_provider()

    def _build_token_provider(self) -> AliyunTokenProvider:
        if self._settings.aliyun_nls_token:
            return StaticNLSTokenProvider(self._settings.aliyun_nls_token)
        return AliyunCreateTokenProvider(settings=self._settings, client=self._client)

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
        try:
            response = await self._client.post(
                self._settings.aliyun_asr_url,
                params={
                    "appkey": self._settings.aliyun_asr_app_key,
                    "token": token,
                    "format": "wav",
                    "sample_rate": str(self._settings.sample_rate),
                },
                content=audio_data,
                headers={"Content-Type": "application/octet-stream"},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Aliyun ASR request failed: {_format_http_error(exc)}") from exc

        if response.status_code != 200:
            friendly_error = self._build_error_message(response)
            raise RuntimeError(
                f"Aliyun ASR request failed with status {response.status_code}: "
                f"{friendly_error}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Aliyun ASR returned non-JSON response: "
                f"{response.text.strip() or '<empty response>'}"
            ) from exc

        status = payload.get("status")
        if status not in (None, 20000000):
            message = payload.get("message") or payload.get("Message") or response.text
            raise RuntimeError(
                f"Aliyun ASR recognition failed with status {status}: "
                f"{str(message).strip() or '<empty response>'}"
            )

        return self._parse_segments(payload)

    def _build_error_message(self, response: httpx.Response) -> str:
        raw_text = response.text.strip() or "<empty response>"
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return raw_text

        status = payload.get("status")
        message = str(payload.get("message") or payload.get("Message") or raw_text).strip()
        if "FREE_TRIAL_EXPIRED" in message or status == 40000010:
            return (
                "Aliyun ASR free trial has expired. Enable billing or switch to another ASR "
                f"credential before recording again. Raw response: {raw_text}"
            )
        return message or raw_text

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

        if segments:
            logger.info("Aliyun ASR returned %s timestamped transcript segments", len(segments))
            return segments

        text = str(payload.get("result", "")).strip()
        if text:
            logger.info("Aliyun ASR returned a transcript without sentence timestamps")
            return [TranscriptSegment(text=text, start=0.0, end=0.0)]

        logger.info("Aliyun ASR returned no transcript content")
        return []
