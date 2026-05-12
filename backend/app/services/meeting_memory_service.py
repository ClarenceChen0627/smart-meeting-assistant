from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import cast

from app.schemas.meeting_history import MeetingHistoryStatus, MeetingRecord
from app.schemas.memory import (
    MeetingMemoryOverview,
    MemoryCollectionType,
    MemoryActionItem,
    MemoryCollection,
    MemoryDecisionItem,
    MemoryMeetingReference,
    MemoryOpenQuestionItem,
    MemoryRiskItem,
    MemorySourceReference,
    MemoryStats,
    NextMeetingBrief,
)
from app.services.meeting_history_service import MeetingHistoryService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MeetingMemoryService:
    ALL_COLLECTION_ID = "all"

    _OPEN_QUESTION_PATTERN = re.compile(
        r"(\?|open question|unresolved|unclear|tbd|not decided|needs confirmation|"
        r"\b(who|what|when|where|why|how|whether|should|can|could|will)\b)",
        re.IGNORECASE,
    )
    _TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

    def __init__(self, meeting_history_service: MeetingHistoryService) -> None:
        self._meeting_history_service = meeting_history_service

    def get_overview(
        self,
        *,
        collection_id: str | None = None,
        archived: bool | None = False,
    ) -> MeetingMemoryOverview:
        generated_at = _utc_now_iso()
        requested_collection_id = collection_id or self.ALL_COLLECTION_ID
        meetings = self._load_meetings(archived=archived)
        collections = self._build_collections(meetings)
        if not any(collection.collection_id == requested_collection_id for collection in collections):
            raise ValueError("Memory collection not found.")

        selected_meetings = [
            meeting for meeting in meetings if self._matches_collection(meeting, requested_collection_id)
        ]
        selected_collection = next(
            collection for collection in collections if collection.collection_id == requested_collection_id
        )
        action_items = self._build_action_items(selected_meetings)
        decisions = self._build_decisions(selected_meetings)
        risks = self._build_risks(selected_meetings)
        open_questions = self._build_open_questions(selected_meetings)
        stats = self._build_stats(
            selected_meetings,
            action_items=action_items,
            decisions=decisions,
            risks=risks,
            open_questions=open_questions,
        )

        return MeetingMemoryOverview(
            collection_id=requested_collection_id,
            generated_at=generated_at,
            collections=collections,
            stats=stats,
            action_items=action_items,
            decisions=decisions,
            risks=risks,
            open_questions=open_questions,
            next_meeting_brief=self._build_next_meeting_brief(
                collection=selected_collection,
                generated_at=generated_at,
                meetings=selected_meetings,
                action_items=action_items,
                decisions=decisions,
                risks=risks,
                open_questions=open_questions,
            ),
        )

    def _load_meetings(self, *, archived: bool | None) -> list[MeetingRecord]:
        meeting_refs = self._meeting_history_service.list_meetings(archived=archived)
        meetings: list[MeetingRecord] = []
        for meeting_ref in meeting_refs:
            meeting = self._meeting_history_service.get_meeting(meeting_ref.meeting_id)
            if meeting is not None:
                meetings.append(meeting)
        return meetings

    def _build_collections(self, meetings: list[MeetingRecord]) -> list[MemoryCollection]:
        collections = [
            self._collection_from_meetings(
                collection_id=self.ALL_COLLECTION_ID,
                collection_type="all",
                name="All active meetings",
                meetings=meetings,
            )
        ]

        tag_names = sorted({tag for meeting in meetings for tag in meeting.tags}, key=str.lower)
        for tag in tag_names:
            tag_meetings = [meeting for meeting in meetings if tag in meeting.tags]
            collections.append(
                self._collection_from_meetings(
                    collection_id=f"tag:{tag}",
                    collection_type="tag",
                    name=tag,
                    meetings=tag_meetings,
                )
            )

        scene_names = sorted({meeting.scene for meeting in meetings}, key=str.lower)
        for scene in scene_names:
            scene_meetings = [meeting for meeting in meetings if meeting.scene == scene]
            collections.append(
                self._collection_from_meetings(
                    collection_id=f"scene:{scene}",
                    collection_type="scene",
                    name=self._format_scene_name(scene),
                    meetings=scene_meetings,
                )
            )

        return collections

    def _collection_from_meetings(
        self,
        *,
        collection_id: str,
        collection_type: str,
        name: str,
        meetings: list[MeetingRecord],
    ) -> MemoryCollection:
        action_items = self._build_action_items(meetings)
        decisions = self._build_decisions(meetings)
        risks = self._build_risks(meetings)
        open_questions = self._build_open_questions(meetings)
        updated_at = max((meeting.updated_at for meeting in meetings), default=None)
        return MemoryCollection(
            collection_id=collection_id,
            collection_type=cast(MemoryCollectionType, collection_type),
            name=name,
            meeting_count=len(meetings),
            finalized_count=sum(1 for meeting in meetings if meeting.status == MeetingHistoryStatus.FINALIZED),
            open_action_count=sum(1 for item in action_items if item.status != "completed"),
            completed_action_count=sum(1 for item in action_items if item.status == "completed"),
            decision_count=len(decisions),
            risk_count=len(risks),
            open_question_count=len(open_questions),
            updated_at=updated_at,
        )

    def _matches_collection(self, meeting: MeetingRecord, collection_id: str) -> bool:
        if collection_id == self.ALL_COLLECTION_ID:
            return True
        if collection_id.startswith("tag:"):
            return collection_id.removeprefix("tag:") in meeting.tags
        if collection_id.startswith("scene:"):
            return meeting.scene == collection_id.removeprefix("scene:")
        return False

    def _build_action_items(self, meetings: list[MeetingRecord]) -> list[MemoryActionItem]:
        items: list[MemoryActionItem] = []
        for meeting in meetings:
            if not meeting.summary:
                continue
            for index, action_item in enumerate(meeting.summary.action_items):
                if not action_item.is_actionable:
                    continue
                source = self._source_reference(
                    meeting,
                    text=action_item.source_excerpt or action_item.task,
                    transcript_index=action_item.transcript_index,
                )
                items.append(
                    MemoryActionItem(
                        id=f"{meeting.meeting_id}:action:{index}",
                        action_item_index=index,
                        task=action_item.task,
                        assignee=action_item.assignee,
                        deadline=action_item.deadline,
                        status=action_item.status,
                        source_excerpt=action_item.source_excerpt,
                        confidence=action_item.confidence,
                        owner_explicit=action_item.owner_explicit,
                        deadline_explicit=action_item.deadline_explicit,
                        source=source,
                    )
                )
        items.sort(key=lambda item: item.task.lower())
        items.sort(key=lambda item: item.source.updated_at, reverse=True)
        items.sort(key=lambda item: item.deadline.lower() in {"", "not specified"})
        items.sort(key=lambda item: item.status == "completed")
        return items

    def _build_decisions(self, meetings: list[MeetingRecord]) -> list[MemoryDecisionItem]:
        items: list[MemoryDecisionItem] = []
        for meeting in meetings:
            if not meeting.summary:
                continue
            for index, decision in enumerate(meeting.summary.decisions):
                normalized = self._normalize_text(decision)
                if not normalized:
                    continue
                items.append(
                    MemoryDecisionItem(
                        id=f"{meeting.meeting_id}:decision:{index}",
                        decision=normalized,
                        source=self._source_reference(meeting, text=normalized),
                    )
                )
        return sorted(items, key=lambda item: item.source.updated_at, reverse=True)

    def _build_risks(self, meetings: list[MeetingRecord]) -> list[MemoryRiskItem]:
        items: list[MemoryRiskItem] = []
        for meeting in meetings:
            if not meeting.summary:
                continue
            for index, risk in enumerate(meeting.summary.risks):
                normalized = self._normalize_text(risk)
                if not normalized:
                    continue
                items.append(
                    MemoryRiskItem(
                        id=f"{meeting.meeting_id}:risk:{index}",
                        risk=normalized,
                        source=self._source_reference(meeting, text=normalized),
                    )
                )
        return sorted(items, key=lambda item: item.source.updated_at, reverse=True)

    def _build_open_questions(self, meetings: list[MeetingRecord]) -> list[MemoryOpenQuestionItem]:
        items: list[MemoryOpenQuestionItem] = []
        seen: set[tuple[str, str]] = set()
        for meeting in meetings:
            if not meeting.summary:
                continue
            for index, risk in enumerate(meeting.summary.risks):
                normalized = self._normalize_text(risk)
                if not normalized or not self._looks_like_open_question(normalized):
                    continue
                dedupe_key = (meeting.meeting_id, normalized.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                items.append(
                    MemoryOpenQuestionItem(
                        id=f"{meeting.meeting_id}:question:{index}",
                        question=normalized,
                        source=self._source_reference(meeting, text=normalized),
                    )
                )
        return sorted(items, key=lambda item: item.source.updated_at, reverse=True)

    def _build_stats(
        self,
        meetings: list[MeetingRecord],
        *,
        action_items: list[MemoryActionItem],
        decisions: list[MemoryDecisionItem],
        risks: list[MemoryRiskItem],
        open_questions: list[MemoryOpenQuestionItem],
    ) -> MemoryStats:
        return MemoryStats(
            meeting_count=len(meetings),
            finalized_count=sum(1 for meeting in meetings if meeting.status == MeetingHistoryStatus.FINALIZED),
            action_count=len(action_items),
            open_action_count=sum(1 for item in action_items if item.status != "completed"),
            completed_action_count=sum(1 for item in action_items if item.status == "completed"),
            decision_count=len(decisions),
            risk_count=len(risks),
            open_question_count=len(open_questions),
        )

    def _build_next_meeting_brief(
        self,
        *,
        collection: MemoryCollection,
        generated_at: str,
        meetings: list[MeetingRecord],
        action_items: list[MemoryActionItem],
        decisions: list[MemoryDecisionItem],
        risks: list[MemoryRiskItem],
        open_questions: list[MemoryOpenQuestionItem],
    ) -> NextMeetingBrief:
        pending_actions = [item for item in action_items if item.status != "completed"]
        agenda: list[str] = []
        agenda.extend(f"Confirm progress: {item.task}" for item in pending_actions[:3])
        agenda.extend(f"Resolve open question: {item.question}" for item in open_questions[:2])
        agenda.extend(f"Mitigate risk: {item.risk}" for item in risks[:2])
        if decisions:
            agenda.append("Validate whether recent decisions still hold.")
        if not agenda:
            agenda.append("Capture decisions, owners, deadlines, and risks for the next discussion.")

        suggested_focus: list[str] = []
        if any(item.assignee.lower() == "unassigned" or item.deadline.lower() == "not specified" for item in pending_actions):
            suggested_focus.append("Assign clear owners and deadlines.")
        if pending_actions:
            suggested_focus.append("Close pending follow-up work.")
        if open_questions:
            suggested_focus.append("Resolve open questions.")
        if risks:
            suggested_focus.append("Review risk mitigation.")
        if not suggested_focus:
            suggested_focus.append("Confirm the next decision and delivery owner.")

        recent_meetings = [
            self._meeting_reference(meeting)
            for meeting in sorted(meetings, key=lambda item: item.updated_at, reverse=True)[:5]
        ]
        recap = (
            f"{collection.name} has {len(meetings)} active meetings, "
            f"{len(pending_actions)} pending action items, {len(decisions)} decisions, "
            f"{len(risks)} risks, and {len(open_questions)} open questions."
        )
        return NextMeetingBrief(
            collection_id=collection.collection_id,
            collection_name=collection.name,
            generated_at=generated_at,
            recap=recap,
            agenda=agenda[:8],
            suggested_focus=suggested_focus[:5],
            recent_meetings=recent_meetings,
        )

    def _source_reference(
        self,
        meeting: MeetingRecord,
        *,
        text: str,
        transcript_index: int | None = None,
    ) -> MemorySourceReference:
        transcript = None
        if transcript_index is not None:
            transcript = next(
                (item for item in meeting.transcripts if item.transcript_index == transcript_index),
                None,
            )
        if transcript is None:
            transcript = self._find_supporting_transcript(meeting, text)

        return MemorySourceReference(
            **self._meeting_reference(meeting).model_dump(),
            transcript_index=transcript.transcript_index if transcript else transcript_index,
            source_excerpt=transcript.text if transcript else text,
        )

    def _find_supporting_transcript(self, meeting: MeetingRecord, text: str):
        query_tokens = self._tokenize(text)
        if not query_tokens:
            return None
        best_score = 0
        best_transcript = None
        for transcript in meeting.transcripts:
            transcript_tokens = self._tokenize(transcript.text)
            if not transcript_tokens:
                continue
            overlap = len(query_tokens.intersection(transcript_tokens))
            if overlap > best_score:
                best_score = overlap
                best_transcript = transcript
        return best_transcript if best_score > 0 else None

    def _meeting_reference(self, meeting: MeetingRecord) -> MemoryMeetingReference:
        return MemoryMeetingReference(
            meeting_id=meeting.meeting_id,
            title=self._build_meeting_title(meeting),
            created_at=meeting.created_at,
            updated_at=meeting.updated_at,
            scene=meeting.scene,
            source_type=meeting.source_type,
            tags=meeting.tags,
        )

    def _looks_like_open_question(self, value: str) -> bool:
        return bool(self._OPEN_QUESTION_PATTERN.search(value))

    def _tokenize(self, value: str) -> set[str]:
        return {token.lower() for token in self._TOKEN_PATTERN.findall(value) if len(token) > 2}

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.split()).strip()

    @staticmethod
    def _build_meeting_title(meeting: MeetingRecord) -> str:
        if meeting.title.strip():
            return meeting.title.strip()
        if meeting.source_name:
            return meeting.source_name.rsplit(".", 1)[0]
        if meeting.summary and meeting.summary.title.strip():
            return meeting.summary.title.strip()
        return f"{MeetingMemoryService._format_scene_name(meeting.scene)} {meeting.created_at[:10]}"

    @staticmethod
    def _format_scene_name(scene: str) -> str:
        labels = {
            "general": "General meetings",
            "finance": "Finance reviews",
            "hr": "HR / interviews",
        }
        return labels.get(scene, scene.replace("_", " ").title())
