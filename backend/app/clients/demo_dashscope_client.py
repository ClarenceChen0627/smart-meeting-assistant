from __future__ import annotations

import json

from app.core.config import Settings


class DemoDashScopeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return self._settings.demo_mode

    async def aclose(self) -> None:
        return

    async def create_chat_completion(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Demo mode is disabled. Set DEMO_MODE=1 to use demo AI responses.")
        if "overall_sentiment" in system_prompt or "情绪动态" in system_prompt:
            return json.dumps(
                {
                    "overall_sentiment": "mixed",
                    "engagement_level": "high",
                    "engagement_summary": "The demo meeting shows active agreement with one clear risk discussion.",
                    "signal_counts": {
                        "agreement": 1,
                        "disagreement": 0,
                        "tension": 1,
                        "hesitation": 0,
                    },
                    "highlights": [
                        {
                            "transcript_index": 1,
                            "signal": "tension",
                            "severity": "medium",
                            "reason": "The speaker explicitly mentions an integration risk.",
                        }
                    ],
                }
            )

        return json.dumps(
            {
                "title": "Demo Launch Checklist Review",
                "overview": (
                    "The team reviewed the launch checklist, confirmed the plan, "
                    "and called out an integration risk to track before release."
                ),
                "key_topics": ["Launch checklist", "Integration risk", "Engineering follow-up"],
                "decisions": ["Proceed with the launch checklist review plan"],
                "action_items": [
                    {
                        "task": "Send the final launch checklist by Friday",
                        "assignee": "Speaker 1",
                        "deadline": "Friday",
                        "status": "pending",
                        "source_excerpt": "I will send the final checklist by Friday and follow up with engineering.",
                        "transcript_index": 2,
                        "is_actionable": True,
                        "confidence": 0.95,
                        "owner_explicit": True,
                        "deadline_explicit": True,
                    }
                ],
                "risks": ["Integration risk needs follow-up before release"],
            }
        )

    async def translate_text(
        self,
        *,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        if not self.is_configured:
            raise RuntimeError("Demo mode is disabled. Set DEMO_MODE=1 to use demo translation.")
        if not text.strip():
            return ""
        return f"[Demo {target_lang}] {text}"
