from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from app.clients.dashscope_client import DashScopeClient
from app.schemas.summary import ActionItem, MeetingSummary
from app.schemas.transcript import TranscriptItem

logger = logging.getLogger(__name__)


class SummaryService:
    _LIST_PREFIX_PATTERN = re.compile(
        r"^(?:第[一二三四五六七八九十0-9]+[、，,:：\s]*|首先[、，,:：\s]*|其次[、，,:：\s]*|然后[、，,:：\s]*|最后[、，,:：\s]*|first[,:：\s]+|second[,:：\s]+|third[,:：\s]+)",
        re.IGNORECASE,
    )
    _DECISION_KEYWORDS = (
        "decide",
        "decided",
        "decision",
        "agreed",
        "agree",
        "approved",
        "confirm",
        "confirmed",
        "settled",
        "\u51b3\u5b9a",
        "\u786e\u5b9a",
        "\u786e\u8ba4",
        "\u540c\u610f",
        "\u4e00\u81f4",
        "\u5b89\u6392",
    )
    _ACTION_PATTERNS = (
        re.compile(r"\b(i will|i'll|we will|we'll|let me|i can|we can)\b", re.IGNORECASE),
        re.compile(
            r"\b(follow up|send|share|prepare|schedule|set up|deliver|review|submit|check|confirm|update|draft|finalize)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(\u6211\u4f1a|\u6211\u6765|\u6211\u8d1f\u8d23|\u6211\u4eec\u4f1a|\u8ddf\u8fdb|\u53d1\u9001|\u63d0\u4ea4|\u51c6\u5907|\u786e\u8ba4|\u5b89\u6392)"
        ),
    )
    _ACTIONABLE_VERB_PATTERNS = (
        re.compile(
            r"\b(send|share|prepare|schedule|set up|deliver|review|submit|check|confirm|update|draft|finalize|follow up)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(\u53d1\u9001|\u5206\u4eab|\u51c6\u5907|\u63d0\u4ea4|\u6574\u7406|\u786e\u8ba4|\u8ddf\u8fdb|\u66f4\u65b0|\u5b89\u6392|\u5b8c\u6210|\u63a8\u8fdb)"
        ),
    )
    _NON_ACTIONABLE_PATTERNS = (
        re.compile(r"\b(i agree|we agree|i think|we think|i support|we support)\b", re.IGNORECASE),
        re.compile(
            r"(\u4e5f\u8bb8|\u53ef\u80fd|\u6216\u8bb8|\u4e0d\u592a\u786e\u5b9a|\u5982\u679c|\u7b49.+\u540e|\u5f85.+\u540e|\u5148\u51b3\u5b9a|\u652f\u6301\u8fdb\u5165)"
        ),
    )
    _DEADLINE_PATTERNS = (
        re.compile(r"\b(today|tomorrow|tonight|this week|next week|next month|by [A-Za-z]+day)\b", re.IGNORECASE),
        re.compile(r"\bby\s+\w+\b", re.IGNORECASE),
        re.compile(
            r"(\u4eca\u5929|\u660e\u5929|\u4eca\u665a|\u672c\u5468|\u4e0b\u5468|\u4e0b\u4e2a\u6708|\u5468[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5]|\u661f\u671f[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5]|\u6708\u5e95|\u6708\u521d|\u672c\u6708\u5185|\u4e0b\u5468\u524d)"
        ),
    )
    _CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")
    _LATIN_CHAR_PATTERN = re.compile(r"[A-Za-z]")
    _CLAUSE_SPLIT_PATTERN = re.compile(r"[\u3002\uff1b;.!?\uff01\uff1f\n]+")

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

        language_hint = self._detect_primary_language(transcripts)
        user_prompt = self._build_transcript_prompt(transcripts, language_hint)

        try:
            summary = await self._request_summary(
                system_prompt=self._build_system_prompt(scene, language_hint),
                user_prompt=user_prompt,
            )
            summary = self._augment_summary_from_transcripts(summary, transcripts)

            if self._needs_retry(summary):
                logger.info("Summary missing overview or key topics; retrying with stronger prompt.")
                summary = await self._request_summary(
                    system_prompt=self._build_fallback_system_prompt(scene, language_hint),
                    user_prompt=user_prompt,
                )
                summary = self._augment_summary_from_transcripts(summary, transcripts)

            self._log_summary("Summary generated", summary)
            return summary
        except (json.JSONDecodeError, ValidationError, RuntimeError) as exc:
            logger.error("Summary generation failed: %s", exc)
            return MeetingSummary.empty()

    def _build_system_prompt(self, scene: str, language_hint: str) -> str:
        scene_prompt = {
            "finance": "You are a meeting summarization assistant for finance meetings.",
            "hr": "You are a meeting summarization assistant for HR interviews.",
        }.get(
            scene,
            "You are a meeting summarization assistant.",
        )
        return (
            f"{scene_prompt} "
            "Read the provided meeting transcript and return ONLY valid JSON. "
            "Use the same primary language as the transcript and do not translate content. "
            f"Primary language hint: {language_hint}. "
            "Keep the summary concise and focused on the most important points. "
            "Required fields: "
            "1. title: a short meeting title in the transcript language, not a full sentence, ideally 4-10 words or 6-18 Chinese characters. "
            "2. overview: 2-4 concise sentences summarizing the meeting. "
            "3. key_topics: 1-5 short strings describing the main discussion themes. "
            "4. decisions: explicit decisions, agreements, or confirmed outcomes. Use [] if none. "
            "5. action_items: follow-up actions with task, assignee, deadline, status, source_excerpt, transcript_index, is_actionable, confidence, owner_explicit, and deadline_explicit. Include only concrete, trackable actions. Exclude vague intentions, conditions, dependencies, and support statements. Use [] if none. "
            "6. risks: optional blockers, open questions, or unresolved risks. Use [] if none. "
            'Return JSON in exactly this shape: {"title":"...","overview":"...","key_topics":["..."],"decisions":["..."],"action_items":[{"task":"...","assignee":"...","deadline":"...","status":"pending","source_excerpt":"...","transcript_index":0,"is_actionable":true,"confidence":0.92,"owner_explicit":true,"deadline_explicit":true}],"risks":["..."]}. '
            'Prefer transcript speaker names for assignee. Use "Unassigned" when unknown. '
            'Use "Not specified" when the deadline is unclear. '
            "Set owner_explicit to true when the transcript explicitly assigns or self-assigns the task. "
            "Set deadline_explicit to true when the transcript explicitly states a deadline or time boundary. "
            "Set confidence as a number from 0.0 to 1.0 reflecting how likely the item is a real, trackable action item. "
            "Set is_actionable to true only when the item should be shown as a follow-up action. "
            "transcript_index should point to the supporting utterance or be null if unavailable. "
            'Do not treat examples like "maybe we need to reconfirm", "after budget confirmation, schedule another review", or "I will support moving to the next stage" as action_items unless a concrete owner and deliverable are stated. '
            "Do not output markdown or explanatory text."
        )

    def _build_fallback_system_prompt(self, scene: str, language_hint: str) -> str:
        scene_hint = {
            "finance": "Prioritize budget topics, approvals, timelines, owners, dependencies, and risks.",
            "hr": "Prioritize candidate evaluation, interview outcomes, next-round scheduling, requested materials, and open concerns.",
        }.get(
            scene,
            "Prioritize the main discussion themes, explicit outcomes, and concrete follow-up actions.",
        )
        return (
            "You are a strict meeting summarization extractor. "
            f"{scene_hint} "
            "Return ONLY valid JSON and do not invent unsupported facts. "
            "Use the same primary language as the transcript and keep the wording concise. "
            f"Primary language hint: {language_hint}. "
            "title must be a short meeting title, not a full sentence. "
            "Do not leave overview empty unless the transcript itself is empty. "
            "key_topics must contain at least one concrete discussion topic when the transcript has meaningful content. "
            "decisions and action_items may be empty when they are not supported by the transcript. "
            "If a speaker commits to a concrete task or explicitly asks someone to do something, extract it into action_items and capture assignee and deadline when possible. "
            "Do not include conditional, dependent, or non-trackable statements as action_items. "
            'Return JSON in exactly this shape: {"title":"...","overview":"...","key_topics":["..."],"decisions":["..."],"action_items":[{"task":"...","assignee":"...","deadline":"...","status":"pending","source_excerpt":"...","transcript_index":0,"is_actionable":true,"confidence":0.92,"owner_explicit":true,"deadline_explicit":true}],"risks":["..."]}. '
            'Use "Unassigned" when the owner is unclear and "Not specified" when the deadline is unclear. '
            "When you are unsure whether something is truly actionable, set is_actionable to false and lower confidence. "
            "Do not output markdown or explanatory text."
        )

    def _build_transcript_prompt(self, transcripts: list[TranscriptItem], language_hint: str) -> str:
        lines = [f"Primary language hint: {language_hint}", "Transcript:"]
        lines.extend(
            f"[#{item.transcript_index} {item.speaker} {item.start:.2f}s-{item.end:.2f}s] {item.text}"
            for item in transcripts
        )
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

    def _detect_primary_language(self, transcripts: list[TranscriptItem]) -> str:
        text = " ".join(item.text for item in transcripts)
        chinese_count = len(self._CHINESE_CHAR_PATTERN.findall(text))
        latin_count = len(self._LATIN_CHAR_PATTERN.findall(text))

        if chinese_count == 0 and latin_count == 0:
            return "Unknown"
        if chinese_count >= max(8, latin_count):
            return "Chinese"
        if latin_count >= max(12, chinese_count * 2):
            return "English"
        return "Mixed; use the dominant transcript language"

    def _needs_retry(self, summary: MeetingSummary) -> bool:
        return not summary.overview.strip() or not summary.key_topics

    def _augment_summary_from_transcripts(
        self,
        summary: MeetingSummary,
        transcripts: list[TranscriptItem],
    ) -> MeetingSummary:
        decisions = list(summary.decisions)
        action_items = list(summary.action_items)

        for transcript in transcripts:
            for clause in self._split_clauses(transcript.text):
                if not clause:
                    continue
                if not decisions and self._looks_like_decision(clause):
                    decisions.append(self._normalize_text(clause))
                if self._looks_like_action_item(clause) and not self._has_similar_action_item(
                    action_items,
                    clause,
                    transcript_index=transcript.transcript_index,
                ):
                    assignee = self._infer_assignee(clause, transcript)
                    deadline = self._infer_deadline(clause)
                    owner_explicit = self._is_owner_explicit(assignee)
                    deadline_explicit = self._is_deadline_explicit(deadline)
                    action_items.append(
                        ActionItem(
                            task=self._normalize_text(clause),
                            assignee=assignee,
                            deadline=deadline,
                            status="pending",
                            source_excerpt=clause,
                            transcript_index=transcript.transcript_index,
                            is_actionable=True,
                            confidence=self._infer_action_item_confidence(
                                clause,
                                owner_explicit=owner_explicit,
                                deadline_explicit=deadline_explicit,
                            ),
                            owner_explicit=owner_explicit,
                            deadline_explicit=deadline_explicit,
                        )
                    )

        return MeetingSummary(
            title=self._derive_title(summary, transcripts),
            overview=summary.overview.strip(),
            key_topics=self._unique_items(summary.key_topics),
            action_items=self._normalize_action_items(action_items),
            decisions=self._unique_items(decisions),
            risks=self._unique_items(summary.risks),
        )

    def _derive_title(self, summary: MeetingSummary, transcripts: list[TranscriptItem]) -> str:
        candidates = [
            summary.title,
            summary.key_topics[0] if summary.key_topics else "",
            self._first_sentence(summary.overview),
            transcripts[0].text if transcripts else "",
        ]
        for candidate in candidates:
            title = self._normalize_text(candidate)
            if title:
                return title[:80]
        return ""

    def _first_sentence(self, text: str) -> str:
        normalized = " ".join(text.split())
        for separator in ("。", ".", "!", "?", "！", "？"):
            if separator in normalized:
                return normalized.split(separator, 1)[0]
        return normalized

    def _split_clauses(self, text: str) -> list[str]:
        return [part.strip() for part in self._CLAUSE_SPLIT_PATTERN.split(text) if part.strip()]

    def _looks_like_decision(self, clause: str) -> bool:
        lowered = clause.lower()
        return any(keyword in lowered for keyword in self._DECISION_KEYWORDS)

    def _looks_like_action_item(self, clause: str) -> bool:
        normalized = clause.strip()
        if len(normalized) < 4:
            return False
        return any(pattern.search(normalized) for pattern in self._ACTION_PATTERNS)

    def _infer_assignee(self, clause: str, transcript: TranscriptItem) -> str:
        normalized = clause.strip()
        if re.search(r"\b(i will|i'll|i can|let me|we will|we'll)\b", normalized, re.IGNORECASE):
            return transcript.speaker
        if re.search(r"(\u6211\u4f1a|\u6211\u6765|\u6211\u8d1f\u8d23|\u6211\u4eec\u4f1a)", normalized):
            return transcript.speaker
        request_match = re.search(r"^\u8bf7(?P<assignee>.+?)(?:\u5728|\u4e8e)", normalized)
        if request_match:
            assignee = request_match.group("assignee").strip("\uff0c, ")
            if assignee:
                return assignee
        return "Unassigned"

    def _infer_deadline(self, clause: str) -> str:
        for pattern in self._DEADLINE_PATTERNS:
            match = pattern.search(clause)
            if match:
                return match.group(0).strip()
        return "Not specified"

    def _normalize_text(self, text: str) -> str:
        return text.strip().strip("\u3002\uff1b\uff0c,;.!?\uff01\uff1f ")

    def _normalize_action_items(self, items: list[ActionItem]) -> list[ActionItem]:
        normalized: list[ActionItem] = []
        for item in items:
            task = self._normalize_text(item.task)
            if not task:
                continue
            owner_explicit = item.owner_explicit or self._is_owner_explicit(item.assignee)
            deadline_explicit = item.deadline_explicit or self._is_deadline_explicit(item.deadline)
            inferred_confidence = self._infer_action_item_confidence(
                task,
                owner_explicit=owner_explicit,
                deadline_explicit=deadline_explicit,
            )
            confidence = inferred_confidence if abs(float(item.confidence) - 0.5) < 1e-9 else float(item.confidence)
            candidate = ActionItem(
                task=task,
                assignee=item.assignee.strip() or "Unassigned",
                deadline=item.deadline.strip() or "Not specified",
                status=item.status,
                source_excerpt=self._normalize_text(item.source_excerpt) or task,
                transcript_index=item.transcript_index,
                is_actionable=item.is_actionable,
                confidence=confidence,
                owner_explicit=owner_explicit,
                deadline_explicit=deadline_explicit,
            )
            if not self._is_action_item_actionable(candidate):
                continue

            merged = False
            for index, existing in enumerate(normalized):
                if self._are_action_items_equivalent(existing, candidate):
                    normalized[index] = self._select_preferred_action_item(existing, candidate)
                    merged = True
                    break
            if merged:
                continue

            normalized.append(candidate)
        return normalized

    def _has_similar_action_item(
        self,
        items: list[ActionItem],
        clause: str,
        *,
        transcript_index: int | None,
    ) -> bool:
        normalized = self._normalize_action_task_for_matching(clause)
        for item in items:
            if transcript_index is not None and item.transcript_index == transcript_index:
                if self._are_action_texts_similar(item.task, normalized):
                    return True
                if self._are_action_texts_similar(item.source_excerpt, normalized):
                    return True
            if self._are_action_texts_similar(item.task, normalized):
                return True
            if self._are_action_texts_similar(item.source_excerpt, normalized):
                return True
        return False

    def _unique_items(self, items: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = self._normalize_text(item)
            if not cleaned:
                continue
            dedupe_key = cleaned.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            unique.append(cleaned)
        return unique

    def _is_action_item_actionable(self, item: ActionItem) -> bool:
        task = self._normalize_text(item.task)
        if len(task) < 6:
            return False
        if not item.is_actionable:
            return False
        if item.confidence < 0.55:
            return False
        if any(pattern.search(task) for pattern in self._NON_ACTIONABLE_PATTERNS):
            return False

        has_owner = item.owner_explicit
        has_deadline = item.deadline_explicit
        if not has_owner and not has_deadline:
            return False

        return True

    def _normalize_action_task_for_matching(self, text: str) -> str:
        normalized = self._normalize_text(text)
        normalized = self._LIST_PREFIX_PATTERN.sub("", normalized)

        earliest_start: int | None = None
        for pattern in self._ACTIONABLE_VERB_PATTERNS:
            match = pattern.search(normalized)
            if not match:
                continue
            if earliest_start is None or match.start() < earliest_start:
                earliest_start = match.start()

        if earliest_start is not None:
            normalized = normalized[earliest_start:]

        return self._normalize_text(normalized)

    def _compact_action_text(self, text: str) -> str:
        normalized = self._normalize_action_task_for_matching(text).lower()
        normalized = re.sub(r"[\s\u3000]+", "", normalized)
        normalized = re.sub(r"[，。；：、,.!?\"'`“”‘’()\[\]{}<>]", "", normalized)
        normalized = normalized.replace("的", "")
        return normalized

    def _are_action_texts_similar(self, left: str, right: str) -> bool:
        left_compact = self._compact_action_text(left)
        right_compact = self._compact_action_text(right)

        if not left_compact or not right_compact:
            return False
        if left_compact == right_compact:
            return True

        shorter, longer = sorted((left_compact, right_compact), key=len)
        if len(shorter) < 6:
            return False

        if shorter in longer and len(shorter) / len(longer) >= 0.55:
            return True
        return False

    def _are_action_items_equivalent(self, left: ActionItem, right: ActionItem) -> bool:
        if (
            left.transcript_index is not None
            and right.transcript_index is not None
            and left.transcript_index == right.transcript_index
        ):
            if self._are_action_texts_similar(left.task, right.task):
                return True
            if self._are_action_texts_similar(left.source_excerpt, right.source_excerpt):
                return True
            if self._are_action_texts_similar(left.task, right.source_excerpt):
                return True
            if self._are_action_texts_similar(left.source_excerpt, right.task):
                return True

        if self._are_action_texts_similar(left.task, right.task):
            if left.assignee == right.assignee:
                return True
            if left.deadline == right.deadline:
                return True

        return False

    def _select_preferred_action_item(self, left: ActionItem, right: ActionItem) -> ActionItem:
        def rank(item: ActionItem) -> tuple[float, int, int, int, int]:
            return (
                float(item.confidence),
                1 if item.owner_explicit else 0,
                1 if item.deadline_explicit else 0,
                1 if item.is_actionable else 0,
                -len(self._normalize_action_task_for_matching(item.task)),
            )

        preferred = left if rank(left) >= rank(right) else right
        alternate = right if preferred is left else left

        if preferred.source_excerpt == preferred.task and alternate.source_excerpt != alternate.task:
            preferred = preferred.model_copy(
                update={
                    "source_excerpt": alternate.source_excerpt,
                }
            )
        return preferred

    def _infer_action_item_confidence(
        self,
        task: str,
        *,
        owner_explicit: bool,
        deadline_explicit: bool,
    ) -> float:
        normalized = self._normalize_text(task)
        score = 0.45
        if owner_explicit:
            score += 0.25
        if deadline_explicit:
            score += 0.2
        if any(pattern.search(normalized) for pattern in self._ACTIONABLE_VERB_PATTERNS):
            score += 0.1
        if any(pattern.search(normalized) for pattern in self._NON_ACTIONABLE_PATTERNS):
            score -= 0.45
        return max(0.0, min(0.95, score))

    def _is_owner_explicit(self, assignee: str) -> bool:
        return assignee.strip().lower() != "unassigned"

    def _is_deadline_explicit(self, deadline: str) -> bool:
        return deadline.strip().lower() != "not specified"

    def _log_summary(self, message: str, summary: MeetingSummary) -> None:
        logger.info(
            "%s: overview_len=%s, key_topics=%s, decisions=%s, action_items=%s, risks=%s",
            message,
            len(summary.overview),
            len(summary.key_topics),
            len(summary.decisions),
            len(summary.action_items),
            len(summary.risks),
        )

    def _strip_code_fence(self, content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if "\n" in cleaned:
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        return cleaned.strip()
