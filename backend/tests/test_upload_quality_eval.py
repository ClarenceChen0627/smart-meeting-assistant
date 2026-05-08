from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.evaluate_upload_quality import (
    CaseResult,
    CheckResult,
    EvaluationCase,
    ExpectedChecks,
    ManifestError,
    build_json_report,
    evaluate_meeting_record,
    parse_manifest,
    render_markdown_report,
)


def test_parse_manifest_resolves_relative_audio_and_defaults(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    audio_file = audio_dir / "meeting.wav"
    audio_file.write_bytes(b"fake-audio")
    manifest_path = tmp_path / "upload-quality.local.json"
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "qwen-upload",
                        "audio_path": "audio/meeting.wav",
                        "scene": "finance",
                        "provider": "dashscope",
                        "target_lang": "ja",
                        "glossary_terms": ["queue wen=>Qwen", "OKR"],
                        "expected": {
                            "min_transcript_count": 2,
                            "required_terms": ["Qwen"],
                            "max_wer": 0.2,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = parse_manifest(manifest_path)

    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "qwen-upload"
    assert case.audio_path == audio_file.resolve()
    assert case.scene == "finance"
    assert case.provider == "dashscope"
    assert case.target_lang == "ja"
    assert case.glossary_terms == "queue wen=>Qwen\nOKR"
    assert case.allow_provider_fallback is False
    assert case.expected.status == "finalized"
    assert case.expected.min_transcript_count == 2
    assert case.expected.required_terms == ["Qwen"]
    assert case.expected.max_wer == 0.2


def test_parse_manifest_reports_missing_audio(tmp_path: Path) -> None:
    manifest_path = tmp_path / "upload-quality.local.json"
    manifest_path.write_text(
        json.dumps({"cases": [{"id": "missing", "audio_path": "audio/missing.wav"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="does not exist"):
        parse_manifest(manifest_path)


def test_evaluate_meeting_record_checks_upload_quality_signals(tmp_path: Path) -> None:
    case = EvaluationCase(
        case_id="good-case",
        audio_path=tmp_path / "meeting.wav",
        scene="general",
        provider="dashscope",
        target_lang="ja",
        expected=ExpectedChecks(
            min_transcript_count=2,
            required_terms=["Qwen"],
            forbidden_terms=["queue wen"],
            min_speaker_count=2,
            require_final_speakers=True,
            require_translations=True,
            require_summary=True,
            require_action_items=True,
            require_analysis=True,
            reference_transcript="Qwen roadmap is ready I agree with the launch plan",
            max_wer=0.0,
            max_cer=0.0,
        ),
    )
    meeting = {
        "meeting_id": "meeting-1",
        "status": "finalized",
        "provider": "dashscope",
        "transcripts": [
            {
                "text": "Qwen roadmap is ready",
                "speaker": "Speaker 1",
                "speaker_is_final": True,
                "translated_text": "[ja] Qwen roadmap is ready",
                "translated_target_lang": "ja",
            },
            {
                "text": "I agree with the launch plan",
                "speaker": "Speaker 2",
                "speaker_is_final": True,
                "translated_text": "[ja] I agree with the launch plan",
                "translated_target_lang": "ja",
            },
        ],
        "summary": {
            "title": "Launch plan",
            "overview": "The team reviewed the Qwen roadmap.",
            "key_topics": ["Roadmap"],
            "decisions": ["Proceed with launch"],
            "risks": [],
            "action_items": [
                {
                    "task": "Share launch plan",
                    "assignee": "Speaker 1",
                    "is_actionable": True,
                }
            ],
        },
        "analysis": {
            "overall_sentiment": "positive",
            "engagement_level": "high",
            "engagement_summary": "Both speakers contributed.",
            "highlights": [],
            "participants": [],
        },
    }

    result = evaluate_meeting_record(case, meeting)

    assert result.passed is True
    assert result.metrics == {"wer": 0.0, "cer": 0.0}
    assert {check.name for check in result.checks} >= {
        "status",
        "provider",
        "required_term:Qwen",
        "forbidden_term:queue wen",
        "final_speakers",
        "translations",
        "summary",
        "action_items",
        "analysis",
        "wer",
        "cer",
    }


def test_evaluate_meeting_record_fails_provider_fallback_by_default(tmp_path: Path) -> None:
    case = EvaluationCase(
        case_id="fallback-case",
        audio_path=tmp_path / "meeting.wav",
        provider="dashscope",
    )
    meeting = {
        "meeting_id": "meeting-1",
        "status": "finalized",
        "provider": "demo",
        "transcripts": [],
    }

    result = evaluate_meeting_record(case, meeting)

    provider_check = next(check for check in result.checks if check.name == "provider")
    assert result.passed is False
    assert provider_check.passed is False
    assert "dashscope" in provider_check.message
    assert "demo" in provider_check.message


def test_evaluate_meeting_record_fails_text_metric_thresholds(tmp_path: Path) -> None:
    case = EvaluationCase(
        case_id="metric-case",
        audio_path=tmp_path / "meeting.wav",
        expected=ExpectedChecks(
            reference_transcript="hello world",
            max_wer=0.0,
            max_cer=0.0,
        ),
    )
    meeting = {
        "meeting_id": "meeting-1",
        "status": "finalized",
        "provider": "dashscope",
        "transcripts": [{"text": "hello there", "speaker": "Speaker 1"}],
    }

    result = evaluate_meeting_record(case, meeting)

    failed_checks = {check.name for check in result.checks if not check.passed}
    assert result.metrics["wer"] > 0
    assert result.metrics["cer"] > 0
    assert {"wer", "cer"} <= failed_checks


def test_report_uses_audio_filename_and_manual_review_without_absolute_paths(tmp_path: Path) -> None:
    result = CaseResult(
        case_id="case-1",
        audio_filename="meeting.wav",
        scene="general",
        requested_provider="dashscope",
        target_lang="en",
        status="finalized",
        meeting_id="meeting-1",
        actual_provider="dashscope",
        checks=[CheckResult("status", True, "Expected status 'finalized', got 'finalized'.")],
        metrics={"wer": 0.1},
        meeting_record_file="cases/case-1.meeting.json",
    )

    report = build_json_report(
        [result],
        api_base_url="http://localhost:8080",
        generated_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    report_json = json.dumps(report, ensure_ascii=False)
    markdown = render_markdown_report(report)

    assert str(tmp_path) not in report_json
    assert "meeting.wav" in report_json
    assert "Manual review" in markdown
    assert "Transcript accuracy" in markdown
