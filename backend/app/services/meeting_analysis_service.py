from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from app.schemas.analysis import (
    MeetingAnalysis,
    MeetingAnalysisHighlight,
    MeetingEngagementLevel,
    ParticipantAnalysis,
    MeetingSentimentLevel,
    MeetingSignalCounts,
    MeetingSignalType,
)
from app.clients.dashscope_client import DashScopeClient
from app.schemas.glossary import GlossaryTerm
from app.schemas.transcript import TranscriptItem

logger = logging.getLogger(__name__)


class MeetingAnalysisService:
    _SIGNAL_PATTERNS: dict[MeetingSignalType, tuple[str, ...]] = {
        MeetingSignalType.AGREEMENT: (
            "我同意",
            "同意这个方案",
            "可以推进",
            "没问题",
            "支持这个方案",
            "i agree",
            "agree with",
            "yes",
            "yeah",
            "sure",
            "of course",
            "sounds good",
            "works for me",
            "that works",
        ),
        MeetingSignalType.DISAGREEMENT: (
            "我不同意",
            "我不认为这样可行",
            "不合理",
            "不认可",
            "我反对",
            "i disagree",
            "do not agree",
            "don't agree",
            "not feasible",
            "not reasonable",
            "i object",
            "i oppose",
            "won't work",
            "doesn't work",
        ),
        MeetingSignalType.TENSION: (
            "风险太高",
            "这样会出问题",
            "我很担心",
            "压力很大",
            "冲突",
            "risk is high",
            "too risky",
            "concerned",
            "worry",
            "worried",
            "this will fail",
            "pressure",
            "conflict",
            "blocked",
        ),
        MeetingSignalType.HESITATION: (
            "我不太确定",
            "也许",
            "可能需要再确认",
            "再想想",
            "不确定",
            "not sure",
            "i'm not sure",
            "i am not sure",
            "maybe",
            "might need",
            "need to confirm",
            "uncertain",
            "i don't know",
        ),
    }
    _SIGNAL_PRIORITY = (
        MeetingSignalType.TENSION,
        MeetingSignalType.DISAGREEMENT,
        MeetingSignalType.HESITATION,
        MeetingSignalType.AGREEMENT,
    )

    def __init__(self, dashscope_client: DashScopeClient) -> None:
        self._dashscope_client = dashscope_client

    @property
    def is_configured(self) -> bool:
        return self._dashscope_client.is_configured

    async def analyze_meeting(
        self,
        transcripts: list[TranscriptItem],
        scene: str,
        *,
        glossary_terms: list[GlossaryTerm] | None = None,
    ) -> MeetingAnalysis:
        if not transcripts:
            return MeetingAnalysis.empty()
        if not self.is_configured:
            logger.warning("DashScope is not configured; returning rule-based meeting analysis.")
            return self._fallback_rule_based_analysis(transcripts)

        try:
            content = await self._dashscope_client.create_chat_completion(
                system_prompt=self._build_system_prompt(scene, glossary_terms or []),
                user_prompt=self._build_transcript_prompt(transcripts, glossary_terms or []),
            )
            payload = json.loads(self._strip_code_fence(content))
            analysis = MeetingAnalysis.model_validate(payload)
            return self._post_process_highlights(analysis, transcripts)
        except (json.JSONDecodeError, ValidationError, RuntimeError) as exc:
            logger.error("Meeting analysis generation failed: %s", exc)
            return self._fallback_rule_based_analysis(transcripts)

    def _build_system_prompt(self, scene: str, glossary_terms: list[GlossaryTerm]) -> str:
        scene_hint = {
            "finance": "你正在分析一场财务或业务决策会议。",
            "hr": "你正在分析一场 HR 面试或招聘沟通。",
        }.get(scene, "你正在分析一场工作会议。")
        glossary_hint = self._build_glossary_prompt(glossary_terms)
        return (
            f"{scene_hint}"
            f"{glossary_hint}"
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

    def _build_transcript_prompt(self, transcripts: list[TranscriptItem], glossary_terms: list[GlossaryTerm]) -> str:
        lines = self._build_glossary_lines(glossary_terms)
        lines.extend(
            f"[#{index} {item.speaker} {item.start:.2f}s-{item.end:.2f}s] {item.text}"
            for index, item in enumerate(transcripts)
        )
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

    def _post_process_highlights(
        self,
        analysis: MeetingAnalysis,
        transcripts: list[TranscriptItem],
    ) -> MeetingAnalysis:
        candidates = [
            highlight
            for highlight in analysis.highlights
            if self._is_valid_highlight(highlight, transcripts)
        ]
        candidates.extend(self._build_rule_based_highlights(transcripts))
        highlights = self._select_highest_priority_highlights(candidates)
        counts = self._build_signal_counts(highlights)
        return analysis.model_copy(
            update={
                "signal_counts": counts,
                "highlights": highlights,
                "participants": self._build_participant_analyses(transcripts, highlights),
            }
        )

    def _fallback_rule_based_analysis(
        self,
        transcripts: list[TranscriptItem],
        *,
        base_analysis: MeetingAnalysis | None = None,
    ) -> MeetingAnalysis:
        highlights = self._build_rule_based_highlights(transcripts)
        counts = self._build_signal_counts(highlights)

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
            participants=self._build_participant_analyses(transcripts, highlights or base_analysis.highlights),
        )

    def _build_rule_based_highlights(
        self,
        transcripts: list[TranscriptItem],
    ) -> list[MeetingAnalysisHighlight]:
        highlights: list[MeetingAnalysisHighlight] = []
        for index, transcript in enumerate(transcripts):
            for signal in self._SIGNAL_PRIORITY:
                if self._text_matches_signal(transcript.text, signal):
                    highlights.append(
                        MeetingAnalysisHighlight(
                            transcript_index=index,
                            signal=signal,
                            severity="medium",
                            reason=f"句子中出现了明显的 {signal.value} 表达。",
                        )
                    )
                    break
        return highlights

    def _is_valid_highlight(
        self,
        highlight: MeetingAnalysisHighlight,
        transcripts: list[TranscriptItem],
    ) -> bool:
        if highlight.transcript_index < 0 or highlight.transcript_index >= len(transcripts):
            return False
        return self._text_matches_signal(
            transcripts[highlight.transcript_index].text,
            highlight.signal,
        )

    def _text_matches_signal(self, text: str, signal: MeetingSignalType) -> bool:
        if signal == MeetingSignalType.AGREEMENT and self._looks_like_request_without_agreement(text):
            return False
        return any(
            self._contains_phrase(text, pattern)
            for pattern in self._SIGNAL_PATTERNS[signal]
        )

    def _looks_like_request_without_agreement(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not re.search(r"\b(will|can|could|would)\s+you\b", normalized):
            return False
        return not any(
            self._contains_phrase(text, pattern)
            for pattern in self._SIGNAL_PATTERNS[MeetingSignalType.AGREEMENT]
        )

    def _select_highest_priority_highlights(
        self,
        candidates: list[MeetingAnalysisHighlight],
    ) -> list[MeetingAnalysisHighlight]:
        priority = {signal: index for index, signal in enumerate(self._SIGNAL_PRIORITY)}
        by_transcript: dict[int, MeetingAnalysisHighlight] = {}
        for candidate in candidates:
            existing = by_transcript.get(candidate.transcript_index)
            if existing is None or priority[candidate.signal] < priority[existing.signal]:
                by_transcript[candidate.transcript_index] = candidate
        return [
            by_transcript[index]
            for index in sorted(by_transcript)
        ]

    def _build_signal_counts(
        self,
        highlights: list[MeetingAnalysisHighlight],
    ) -> MeetingSignalCounts:
        counts = MeetingSignalCounts()
        for highlight in highlights:
            current = getattr(counts, highlight.signal.value)
            setattr(counts, highlight.signal.value, current + 1)
        return counts

    def _build_participant_analyses(
        self,
        transcripts: list[TranscriptItem],
        highlights: list[MeetingAnalysisHighlight],
    ) -> list[ParticipantAnalysis]:
        speaker_stats: dict[str, dict[str, object]] = {}
        for transcript in transcripts:
            speaker = transcript.speaker or "Unknown"
            stats = speaker_stats.setdefault(
                speaker,
                {
                    "transcript_count": 0,
                    "speaking_time_seconds": 0.0,
                    "highlights": [],
                },
            )
            stats["transcript_count"] = int(stats["transcript_count"]) + 1
            duration = max(0.0, transcript.end - transcript.start)
            stats["speaking_time_seconds"] = float(stats["speaking_time_seconds"]) + duration

        for highlight in highlights:
            if highlight.transcript_index < 0 or highlight.transcript_index >= len(transcripts):
                continue
            speaker = transcripts[highlight.transcript_index].speaker or "Unknown"
            stats = speaker_stats.setdefault(
                speaker,
                {
                    "transcript_count": 0,
                    "speaking_time_seconds": 0.0,
                    "highlights": [],
                },
            )
            cast_highlights = stats["highlights"]
            if isinstance(cast_highlights, list):
                cast_highlights.append(highlight)

        participants: list[ParticipantAnalysis] = []
        max_transcript_count = max(
            (int(stats["transcript_count"]) for stats in speaker_stats.values()),
            default=1,
        )
        for speaker, stats in speaker_stats.items():
            speaker_highlights = [
                highlight
                for highlight in stats["highlights"]
                if isinstance(highlight, MeetingAnalysisHighlight)
            ]
            counts = self._build_signal_counts(speaker_highlights)
            total_signals = counts.agreement + counts.disagreement + counts.tension + counts.hesitation
            negative_signals = counts.disagreement + counts.tension
            if negative_signals and counts.agreement:
                sentiment = MeetingSentimentLevel.MIXED
            elif negative_signals:
                sentiment = MeetingSentimentLevel.NEGATIVE
            elif counts.agreement:
                sentiment = MeetingSentimentLevel.POSITIVE
            else:
                sentiment = MeetingSentimentLevel.NEUTRAL

            transcript_count = int(stats["transcript_count"])
            if total_signals >= 2 or transcript_count >= max(3, max_transcript_count):
                engagement = MeetingEngagementLevel.HIGH
            elif total_signals >= 1 or transcript_count > 0:
                engagement = MeetingEngagementLevel.MEDIUM
            else:
                engagement = MeetingEngagementLevel.LOW

            participants.append(
                ParticipantAnalysis(
                    speaker=speaker,
                    transcript_count=transcript_count,
                    speaking_time_seconds=round(float(stats["speaking_time_seconds"]), 2),
                    signal_counts=counts,
                    sentiment=sentiment,
                    engagement_level=engagement,
                    engagement_summary=self._build_participant_summary(
                        speaker,
                        transcript_count=transcript_count,
                        total_signals=total_signals,
                    ),
                )
            )
        return sorted(participants, key=lambda item: (-item.transcript_count, item.speaker))

    @staticmethod
    def _build_participant_summary(
        speaker: str,
        *,
        transcript_count: int,
        total_signals: int,
    ) -> str:
        if total_signals:
            return f"{speaker} contributed {transcript_count} utterances with {total_signals} interaction signals."
        return f"{speaker} contributed {transcript_count} utterances with no explicit interaction signals."

    @staticmethod
    def _build_glossary_prompt(terms: list[GlossaryTerm]) -> str:
        if not terms:
            return ""
        lines = ["自定义术语表如下，分析时请按这些术语理解，不要改写专有名词："]
        for term in terms:
            if term.replacement:
                lines.append(f"{term.term} => {term.replacement}")
            elif term.note:
                lines.append(f"{term.term}: {term.note}")
            else:
                lines.append(term.term)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_glossary_lines(terms: list[GlossaryTerm]) -> list[str]:
        if not terms:
            return []
        lines = ["Glossary:"]
        for term in terms:
            if term.replacement:
                lines.append(f"- {term.term} => {term.replacement}")
            elif term.note:
                lines.append(f"- {term.term}: {term.note}")
            else:
                lines.append(f"- {term.term}")
        lines.append("Transcript:")
        return lines

    @staticmethod
    def _contains_phrase(text: str, pattern: str) -> bool:
        normalized_text = MeetingAnalysisService._normalize_text(text)
        normalized_pattern = MeetingAnalysisService._normalize_text(pattern)
        if re.fullmatch(r"[a-z0-9][a-z0-9' ]*[a-z0-9]", normalized_pattern):
            return re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_pattern)}(?![a-z0-9])",
                normalized_text,
            ) is not None
        return normalized_pattern in normalized_text

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text.casefold()).strip()
