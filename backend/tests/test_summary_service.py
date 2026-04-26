from __future__ import annotations

import asyncio

from app.schemas.transcript import TranscriptItem
from app.services.summary_service import SummaryService


class StubDashScopeClient:
    def __init__(self, responses: list[str] | str) -> None:
        self._responses = [responses] if isinstance(responses, str) else list(responses)
        self.is_configured = True
        self.call_count = 0

    async def create_chat_completion(self, *, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        if not self._responses:
            raise AssertionError("No stub response remaining")
        return self._responses.pop(0)


def test_generate_summary_parses_docs_aligned_fields() -> None:
    client = StubDashScopeClient(
        """
        {
          "title": "Weekly Report Delivery",
          "overview": "The team reviewed the weekly report and aligned on the delivery plan. They confirmed the final owner and timeline for the update.",
          "key_topics": ["Weekly report", "Delivery plan"],
          "decisions": ["Finalize the weekly report on Friday"],
          "action_items": [
            {
              "task": "Send the report by Friday",
              "assignee": "Speaker 1",
              "deadline": "Friday",
              "status": "pending",
              "source_excerpt": "I will send the report by Friday.",
              "transcript_index": 0,
              "is_actionable": true,
              "confidence": 0.93,
              "owner_explicit": true,
              "deadline_explicit": true
            }
          ],
          "risks": []
        }
        """
    )
    service = SummaryService(client)
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the report by Friday.",
            start=0.0,
            end=2.0,
        )
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert summary.overview.startswith("The team reviewed")
    assert summary.title == "Weekly Report Delivery"
    assert summary.key_topics == ["Weekly report", "Delivery plan"]
    assert summary.decisions == ["Finalize the weekly report on Friday"]
    assert len(summary.action_items) == 1
    assert summary.action_items[0].assignee == "Speaker 1"
    assert summary.action_items[0].deadline == "Friday"
    assert summary.action_items[0].transcript_index == 0
    assert summary.action_items[0].is_actionable is True
    assert summary.action_items[0].confidence == 0.93
    assert summary.action_items[0].owner_explicit is True
    assert summary.action_items[0].deadline_explicit is True


def test_generate_summary_retries_when_overview_or_key_topics_are_missing() -> None:
    client = StubDashScopeClient(
        [
            """
            {
              "title": "",
              "overview": "",
              "key_topics": [],
              "decisions": [],
              "action_items": [],
              "risks": []
            }
            """,
            """
            {
              "title": "Launch plan status update",
              "overview": "The meeting focused on the launch plan and clarified who will send the status update. The team left with one concrete follow-up action.",
              "key_topics": ["Launch plan", "Status update"],
              "decisions": ["Proceed with the launch status update"],
              "action_items": [],
              "risks": []
            }
            """,
        ]
    )
    service = SummaryService(client)
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 3",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the launch status update tomorrow.",
            start=0.0,
            end=2.0,
        )
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert client.call_count == 2
    assert summary.title == "Launch plan status update"
    assert summary.overview.startswith("The meeting focused on the launch plan")
    assert summary.key_topics == ["Launch plan", "Status update"]
    assert summary.action_items
    assert summary.action_items[0].assignee == "Speaker 3"


def test_generate_summary_augments_action_items_from_transcripts_when_missing() -> None:
    service = SummaryService(
        StubDashScopeClient(
            """
            {
              "overview": "The team reviewed the updated deck and discussed next steps. One follow-up action was stated explicitly.",
              "key_topics": ["Updated deck", "Next steps"],
              "action_items": [],
              "decisions": [],
              "risks": []
            }
            """
        )
    )
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 2",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the updated deck by Friday and follow up next week.",
            start=0.0,
            end=3.0,
        )
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert summary.action_items
    assert summary.title == "Updated deck"
    first_item = summary.action_items[0]
    assert first_item.assignee == "Speaker 2"
    assert first_item.deadline == "by Friday"
    assert first_item.status == "pending"
    assert first_item.transcript_index == 0
    assert first_item.is_actionable is True
    assert first_item.owner_explicit is True
    assert first_item.deadline_explicit is True
    assert first_item.confidence >= 0.8


def test_generate_summary_does_not_fabricate_overview_from_transcripts() -> None:
    service = SummaryService(
        StubDashScopeClient(
            [
                """
                {
                  "overview": "",
                  "key_topics": [],
                  "action_items": [],
                  "decisions": [],
                  "risks": []
                }
                """,
                """
                {
                  "overview": "",
                  "key_topics": [],
                  "action_items": [],
                  "decisions": [],
                  "risks": []
                }
                """,
            ]
        )
    )
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 4",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the final notes tomorrow.",
            start=0.0,
            end=1.5,
        )
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert summary.overview == ""
    assert summary.key_topics == []
    assert summary.action_items
    assert summary.action_items[0].task == "I will send the final notes tomorrow"
    assert summary.action_items[0].is_actionable is True
    assert summary.action_items[0].deadline_explicit is True


def test_generate_summary_uses_model_actionability_metadata_to_filter_items() -> None:
    service = SummaryService(
        StubDashScopeClient(
            """
            {
              "overview": "The meeting assigned one concrete deliverable and discussed one tentative idea.",
              "key_topics": ["Deliverables", "Tentative idea"],
              "action_items": [
                {
                  "task": "Maybe revisit the rollout plan later",
                  "assignee": "Speaker 1",
                  "deadline": "Tomorrow",
                  "status": "pending",
                  "source_excerpt": "Maybe revisit the rollout plan later.",
                  "transcript_index": 0,
                  "is_actionable": false,
                  "confidence": 0.24,
                  "owner_explicit": true,
                  "deadline_explicit": true
                },
                {
                  "task": "Send the rollout checklist tomorrow",
                  "assignee": "Speaker 1",
                  "deadline": "Tomorrow",
                  "status": "pending",
                  "source_excerpt": "I will send the rollout checklist tomorrow.",
                  "transcript_index": 1,
                  "is_actionable": true,
                  "confidence": 0.91,
                  "owner_explicit": true,
                  "deadline_explicit": true
                }
              ],
              "decisions": [],
              "risks": []
            }
            """
        )
    )
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="Maybe revisit the rollout plan later.",
            start=0.0,
            end=1.0,
        ),
        TranscriptItem(
            transcript_index=1,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the rollout checklist tomorrow.",
            start=1.0,
            end=2.0,
        ),
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert len(summary.action_items) == 1
    assert summary.action_items[0].task == "Send the rollout checklist tomorrow"
    assert summary.action_items[0].confidence == 0.91


def test_generate_summary_deduplicates_model_and_transcript_variants_of_same_action_item() -> None:
    service = SummaryService(
        StubDashScopeClient(
            """
            {
              "overview": "The meeting ended with two concrete follow-up actions.",
              "key_topics": ["Project portfolio", "Launch scope"],
              "action_items": [
                {
                  "task": "整理并提交最新的项目作品集",
                  "assignee": "Speaker 1",
                  "deadline": "本周五之前",
                  "status": "pending",
                  "source_excerpt": "我会在这周五之前整理并提交最新的项目作品集。",
                  "transcript_index": 0,
                  "is_actionable": true,
                  "confidence": 0.95,
                  "owner_explicit": true,
                  "deadline_explicit": true
                },
                {
                  "task": "确认接口稳定性和上线范围",
                  "assignee": "产品和后端同学",
                  "deadline": "下周一之前",
                  "status": "pending",
                  "source_excerpt": "请产品和后端同学在下周一之前确认接口稳定性和上线范围。",
                  "transcript_index": 1,
                  "is_actionable": true,
                  "confidence": 0.94,
                  "owner_explicit": true,
                  "deadline_explicit": true
                }
              ],
              "decisions": [],
              "risks": []
            }
            """
        )
    )
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="第一个，我会在这周五之前整理并提交最新的项目作品集。",
            start=0.0,
            end=2.0,
        ),
        TranscriptItem(
            transcript_index=1,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="第二，请产品和后端同学在下周一之前确认接口稳定性和上线的范围。",
            start=2.0,
            end=4.0,
        ),
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert len(summary.action_items) == 2
    assert summary.action_items[0].task == "整理并提交最新的项目作品集"
    assert summary.action_items[0].assignee == "Speaker 1"
    assert summary.action_items[0].deadline == "本周五之前"
    assert summary.action_items[1].task == "确认接口稳定性和上线范围"
    assert summary.action_items[1].assignee == "产品和后端同学"
    assert summary.action_items[1].deadline == "下周一之前"


def test_generate_summary_filters_vague_and_conditional_action_items() -> None:
    service = SummaryService(
        StubDashScopeClient(
            """
            {
              "overview": "The meeting clarified the current release decision and listed the required follow-up checks.",
              "key_topics": ["Release timing", "Budget and interface confirmation"],
              "action_items": [
                {
                  "task": "也许我们需要再确认一下时间安排和资源投入",
                  "assignee": "Unassigned",
                  "deadline": "Not specified",
                  "status": "pending",
                  "source_excerpt": "也许我们需要再确认一下时间安排和资源投入。",
                  "transcript_index": 0
                },
                {
                  "task": "等接口和预算确认完成后，再安排下一轮评审",
                  "assignee": "Unassigned",
                  "deadline": "Not specified",
                  "status": "pending",
                  "source_excerpt": "等接口和预算确认完成后，再安排下一轮评审。",
                  "transcript_index": 1
                },
                {
                  "task": "我会支持进入下一阶段",
                  "assignee": "Speaker 1",
                  "deadline": "Not specified",
                  "status": "pending",
                  "source_excerpt": "我会支持进入下一阶段。",
                  "transcript_index": 2
                },
                {
                  "task": "整理并提交最新的项目作品集",
                  "assignee": "Speaker 1",
                  "deadline": "这周五之前",
                  "status": "pending",
                  "source_excerpt": "我会在这周五之前整理并提交最新的项目作品集。",
                  "transcript_index": 3
                }
              ],
              "decisions": ["本周不进行上线"],
              "risks": []
            }
            """
        )
    )
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="也许我们需要再确认一下时间安排和资源投入。",
            start=0.0,
            end=2.0,
        ),
        TranscriptItem(
            transcript_index=1,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="等接口和预算确认完成后，再安排下一轮评审。",
            start=2.0,
            end=4.0,
        ),
        TranscriptItem(
            transcript_index=2,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="我会支持进入下一阶段。",
            start=4.0,
            end=5.0,
        ),
        TranscriptItem(
            transcript_index=3,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="我会在这周五之前整理并提交最新的项目作品集。",
            start=5.0,
            end=7.0,
        ),
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert len(summary.action_items) == 1
    assert summary.action_items[0].task == "整理并提交最新的项目作品集"
    assert summary.action_items[0].assignee == "Speaker 1"
    assert summary.action_items[0].deadline == "这周五之前"


def test_generate_summary_does_not_augment_conditional_decision_sentence_as_action_item() -> None:
    service = SummaryService(
        StubDashScopeClient(
            """
            {
              "overview": "The meeting deferred the launch and linked the next review to pending confirmations.",
              "key_topics": ["Launch timing", "Pending confirmations"],
              "action_items": [],
              "decisions": ["本周不进行上线，待进一步确认后再安排评审"],
              "risks": []
            }
            """
        )
    )
    transcripts = [
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="我们今天先决定，不在本周上线，等接口和预算确认完成后，再安排下一轮评审。",
            start=0.0,
            end=4.0,
        )
    ]

    summary = asyncio.run(service.generate_summary(transcripts, "general"))

    assert summary.action_items == []
    assert summary.decisions == ["本周不进行上线，待进一步确认后再安排评审"]
