from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.schemas.analysis import (
    MeetingAnalysis,
    MeetingAnalysisHighlight,
    MeetingEngagementLevel,
    MeetingSentimentLevel,
    MeetingSignalCounts,
    MeetingSignalType,
)
from app.clients.dashscope_client import DashScopeClient
from app.schemas.transcript import TranscriptItem

logger = logging.getLogger(__name__)


class SentimentAnalysisService:
    _SIGNAL_PATTERNS: dict[MeetingSignalType, tuple[str, ...]] = {
        MeetingSignalType.AGREEMENT: ("我同意", "同意这个方案", "可以推进", "没问题", "支持这个方案"),
        MeetingSignalType.DISAGREEMENT: ("我不同意", "我不认为这样可行", "不合理", "不认可", "我反对"),
        MeetingSignalType.TENSION: ("风险太高", "这样会出问题", "我很担心", "压力很大", "冲突"),
        MeetingSignalType.HESITATION: ("我不太确定", "也许", "可能需要再确认", "再想想", "不确定"),
    }

    def __init__(self, dashscope_client: DashScopeClient) -> None:
        self._dashscope_client = dashscope_client

    @property
    def is_configured(self) -> bool:
        return self._dashscope_client.is_configured

    async def analyze_meeting(
        self,
        transcripts: list[TranscriptItem],
        scene: str,
    ) -> MeetingAnalysis:
        if not transcripts:
            return MeetingAnalysis.empty()
        if not self.is_configured:
            logger.warning("DashScope is not configured; returning empty meeting analysis.")
            return MeetingAnalysis.empty()

        try:
            content = await self._dashscope_client.create_chat_completion(
                system_prompt=self._build_system_prompt(scene),
                user_prompt=self._build_transcript_prompt(transcripts),
            )
            payload = json.loads(self._strip_code_fence(content))
            analysis = MeetingAnalysis.model_validate(payload)
            return self._augment_with_rule_based_highlights(analysis, transcripts)
        except (json.JSONDecodeError, ValidationError, RuntimeError) as exc:
            logger.error("Meeting analysis generation failed: %s", exc)
            return self._fallback_rule_based_analysis(transcripts)

    def _build_system_prompt(self, scene: str) -> str:
        scene_hint = {
            "finance": "你正在分析一场财务或业务决策会议。",
            "hr": "你正在分析一场 HR 面试或招聘沟通。",
        }.get(scene, "你正在分析一场工作会议。")
        return (
            f"{scene_hint}"
            "请分析转写中的情绪动态与参与度模式。"
            "你必须特别关注四类互动信号："
            "1. agreement：明确同意、认可、支持，例如“我同意”“可以推进”“没问题”；"
            "2. disagreement：明确反对、否定、质疑，例如“我不同意”“我不认为这样可行”“这不合理”；"
            "3. tension：明显紧张、冲突、强烈担忧，例如“风险太高”“这样会出问题”“我很担心”；"
            "4. hesitation：明显犹豫、不确定、保留，例如“我不太确定”“也许”“可能需要再确认”。"
            "只根据 transcript 内容判断，不要编造。"
            "如果文本中明确出现上述表达，就应当计入 signal_counts，并尽量加入 highlights。"
            "返回 JSON only，格式必须严格为："
            '{"overall_sentiment":"positive|neutral|negative|mixed",'
            '"engagement_level":"low|medium|high",'
            '"engagement_summary":"...",'
            '"signal_counts":{"agreement":0,"disagreement":0,"tension":0,"hesitation":0},'
            '"highlights":[{"transcript_index":0,"signal":"agreement|disagreement|tension|hesitation","severity":"low|medium|high","reason":"..."}]} '
            "highlights 里的 transcript_index 必须引用具体原句编号。"
            "如果没有明显信号，highlights 可以为空，但不要忽略明确的同意、反对、紧张、犹豫表达。"
        )

    def _build_transcript_prompt(self, transcripts: list[TranscriptItem]) -> str:
        lines = [
            f"[#{index} {item.speaker} {item.start:.2f}s-{item.end:.2f}s] {item.text}"
            for index, item in enumerate(transcripts)
        ]
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

    def _augment_with_rule_based_highlights(
        self,
        analysis: MeetingAnalysis,
        transcripts: list[TranscriptItem],
    ) -> MeetingAnalysis:
        if analysis.highlights:
            return analysis
        return self._fallback_rule_based_analysis(transcripts, base_analysis=analysis)

    def _fallback_rule_based_analysis(
        self,
        transcripts: list[TranscriptItem],
        *,
        base_analysis: MeetingAnalysis | None = None,
    ) -> MeetingAnalysis:
        highlights: list[MeetingAnalysisHighlight] = []
        counts = MeetingSignalCounts()

        for index, transcript in enumerate(transcripts):
            text = transcript.text
            for signal, patterns in self._SIGNAL_PATTERNS.items():
                if any(pattern in text for pattern in patterns):
                    highlights.append(
                        MeetingAnalysisHighlight(
                            transcript_index=index,
                            signal=signal,
                            severity="medium",
                            reason=f"句子中出现了明显的 {signal.value} 表达。",
                        )
                    )
                    current = getattr(counts, signal.value)
                    setattr(counts, signal.value, current + 1)
                    break

        if base_analysis is None:
            base_analysis = MeetingAnalysis.empty()

        overall_sentiment = base_analysis.overall_sentiment
        if counts.disagreement or counts.tension:
            overall_sentiment = MeetingSentimentLevel.MIXED
        elif counts.agreement and not (counts.disagreement or counts.tension or counts.hesitation):
            overall_sentiment = MeetingSentimentLevel.POSITIVE

        engagement_level = base_analysis.engagement_level
        total_signals = counts.agreement + counts.disagreement + counts.tension + counts.hesitation
        if total_signals >= 3:
            engagement_level = MeetingEngagementLevel.HIGH
        elif total_signals >= 1:
            engagement_level = MeetingEngagementLevel.MEDIUM

        engagement_summary = base_analysis.engagement_summary
        if highlights:
            engagement_summary = "Discussion includes explicit interaction signals worth reviewing."

        return MeetingAnalysis(
            overall_sentiment=overall_sentiment,
            engagement_level=engagement_level,
            engagement_summary=engagement_summary,
            signal_counts=counts if total_signals else base_analysis.signal_counts,
            highlights=highlights or base_analysis.highlights,
        )
