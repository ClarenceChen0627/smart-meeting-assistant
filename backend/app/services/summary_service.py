from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.clients.dashscope_client import DashScopeClient
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptItem

logger = logging.getLogger(__name__)


class SummaryService:
    _TODO_KEYWORDS = (
        "补充",
        "提交",
        "准备",
        "跟进",
        "确认",
        "发送",
        "提供",
        "完成",
        "整理",
        "联系",
    )
    _DECISION_KEYWORDS = (
        "会安排",
        "将安排",
        "安排",
        "决定",
        "确定",
        "下周",
        "二面",
        "下一轮",
        "后续",
        "流程",
    )

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

        user_prompt = self._build_transcript_prompt(transcripts)
        try:
            summary = await self._request_summary(
                system_prompt=self._build_system_prompt(scene),
                user_prompt=user_prompt,
            )
            summary = self._augment_summary_from_transcripts(summary, transcripts)
            if self._has_content(summary):
                logger.info(
                    "Summary generated with %s todos, %s decisions, %s risks",
                    len(summary.todos),
                    len(summary.decisions),
                    len(summary.risks),
                )
                return summary

            logger.info("Summary returned empty result; retrying with stronger extraction prompt.")
            fallback_summary = await self._request_summary(
                system_prompt=self._build_fallback_system_prompt(scene),
                user_prompt=user_prompt,
            )
            fallback_summary = self._augment_summary_from_transcripts(fallback_summary, transcripts)
            logger.info(
                "Fallback summary generated with %s todos, %s decisions, %s risks",
                len(fallback_summary.todos),
                len(fallback_summary.decisions),
                len(fallback_summary.risks),
            )
            return fallback_summary
        except (json.JSONDecodeError, ValidationError, RuntimeError) as exc:
            logger.error("Summary generation failed: %s", exc)
            return MeetingSummary.empty()

    def _build_system_prompt(self, scene: str) -> str:
        scene_prompt = {
            "finance": "你是财务会议纪要助手。",
            "hr": "你是 HR 面试纪要助手。",
        }.get(
            scene,
            "你是会议纪要助手。",
        )
        return (
            f"{scene_prompt}"
            "请严格依据转写内容提取并输出 JSON，总结以下三类信息："
            "1. todos：明确的待办、跟进动作、待提交材料、待安排事项；"
            "2. decisions：已确认的安排、结论、下一步流程、时间节点；"
            "3. risks：风险、疑问、能力缺口、待确认事项。"
            '输出格式必须是 {"todos":["..."],"decisions":["..."],"risks":["..."]}。'
            "不要输出 markdown，不要输出解释。"
        )

    def _build_fallback_system_prompt(self, scene: str) -> str:
        scene_hint = {
            "finance": "财务会议里，预算、审批、时间安排、责任人、风险敞口都应优先提取。",
            "hr": "HR 面试里，下一轮安排、补充材料、面试结论、候选人短板与待确认项都应优先提取。",
        }.get(
            scene,
            "会议里出现的后续动作、安排、结论、待确认事项都应优先提取。",
        )
        return (
            "你是一个非常严格的中文会议总结抽取器。"
            f"{scene_hint}"
            "请只根据提供的转写做信息抽取，不要编造。"
            "如果转写中出现了明确安排、下一步动作、时间点、需要补充的内容，"
            "则 todos 和 decisions 不能同时为空。"
            "risks 允许为空，但如果出现了能力短板、延期、预算、待确认项、顾虑，就必须写入 risks。"
            '输出格式必须是 {"todos":["..."],"decisions":["..."],"risks":["..."]}。'
            "每一项尽量简洁，用中文短句表达。不要输出任何额外文字。"
        )

    def _build_transcript_prompt(self, transcripts: list[TranscriptItem]) -> str:
        lines = [
            f"[{item.speaker} {item.start:.2f}s-{item.end:.2f}s] {item.text}"
            for item in transcripts
        ]
        return "\n".join(lines)

    async def _request_summary(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> MeetingSummary:
        content = await self._dashscope_client.create_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        payload = json.loads(self._strip_code_fence(content))
        return MeetingSummary.model_validate(payload)

    def _has_content(self, summary: MeetingSummary) -> bool:
        return bool(summary.todos or summary.decisions or summary.risks)

    def _augment_summary_from_transcripts(
        self,
        summary: MeetingSummary,
        transcripts: list[TranscriptItem],
    ) -> MeetingSummary:
        if summary.todos and summary.decisions:
            return summary

        todos = list(summary.todos)
        decisions = list(summary.decisions)
        risks = list(summary.risks)

        for transcript in transcripts:
            for clause in self._split_clauses(transcript.text):
                if not clause:
                    continue
                if not todos and self._looks_like_todo(clause):
                    todos.append(clause)
                if not decisions and self._looks_like_decision(clause):
                    decisions.append(clause)

        return MeetingSummary(
            todos=self._unique_items(todos),
            decisions=self._unique_items(decisions),
            risks=self._unique_items(risks),
        )

    def _split_clauses(self, text: str) -> list[str]:
        normalized = text.replace("。", "，").replace("；", "，").replace(",", "，")
        return [part.strip() for part in normalized.split("，") if part.strip()]

    def _looks_like_todo(self, clause: str) -> bool:
        return any(keyword in clause for keyword in self._TODO_KEYWORDS)

    def _looks_like_decision(self, clause: str) -> bool:
        return any(keyword in clause for keyword in self._DECISION_KEYWORDS)

    def _unique_items(self, items: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            unique.append(cleaned)
        return unique

    def _strip_code_fence(self, content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if "\n" in cleaned:
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        return cleaned.strip()
