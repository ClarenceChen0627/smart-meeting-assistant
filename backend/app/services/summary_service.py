from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.clients.dashscope_client import DashScopeClient
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptItem

logger = logging.getLogger(__name__)


class SummaryService:
    def __init__(self, dashscope_client: DashScopeClient) -> None:
        self._dashscope_client = dashscope_client

    @property
    def is_configured(self) -> bool:
        return self._dashscope_client.is_configured

    async def generate_summary(
        self,
        transcripts: list[TranscriptItem],
        scene: str,
    ) -> MeetingSummary:
        if not transcripts:
            return MeetingSummary.empty()
        if not self.is_configured:
            logger.warning("DashScope is not configured; returning empty summary.")
            return MeetingSummary.empty()

        system_prompt = self._build_system_prompt(scene)
        user_prompt = self._build_transcript_prompt(transcripts)
        try:
            content = await self._dashscope_client.create_chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            payload = json.loads(self._strip_code_fence(content))
            return MeetingSummary.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, RuntimeError) as exc:
            logger.error("Summary generation failed: %s", exc)
            return MeetingSummary.empty()

    def _build_system_prompt(self, scene: str) -> str:
        scene_prompt = {
            "finance": (
                "You are a finance meeting assistant. Extract actionable todos, decisions, "
                "and risks from the transcript."
            ),
            "hr": (
                "You are an HR interview assistant. Extract actionable todos, decisions, "
                "and risks from the transcript."
            ),
        }.get(
            scene,
            "You are a meeting assistant. Extract actionable todos, decisions, and risks.",
        )
        return (
            f"{scene_prompt} "
            "Return JSON only with this exact shape: "
            '{"todos":["..."],"decisions":["..."],"risks":["..."]}. '
            "Do not include markdown fences or prose."
        )

    def _build_transcript_prompt(self, transcripts: list[TranscriptItem]) -> str:
        lines = [f"[{item.speaker}] {item.text}" for item in transcripts]
        return "\n".join(lines)

    def _strip_code_fence(self, content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if "\n" in cleaned:
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        return cleaned.strip()
