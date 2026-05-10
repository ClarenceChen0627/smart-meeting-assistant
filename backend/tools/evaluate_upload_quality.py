from __future__ import annotations

import argparse
import contextlib
import json
import mimetypes
import re
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


FINAL_STATUSES = {"finalized", "failed"}


class EvaluationError(RuntimeError):
    """Base error for upload quality evaluation failures."""


class ManifestError(EvaluationError):
    """Raised when the manifest cannot be parsed or validated."""


@dataclass(frozen=True)
class ExpectedChecks:
    status: str = "finalized"
    min_transcript_count: int | None = None
    required_terms: list[str] = field(default_factory=list)
    forbidden_terms: list[str] = field(default_factory=list)
    min_speaker_count: int | None = None
    require_final_speakers: bool = False
    require_translations: bool = False
    require_summary: bool = False
    require_action_items: bool = False
    require_analysis: bool = False
    reference_transcript: str | None = None
    max_wer: float | None = None
    max_cer: float | None = None


@dataclass(frozen=True)
class CostProfile:
    provider: str
    currency: str
    asr_per_audio_minute: float


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    audio_path: Path
    scene: str = "general"
    provider: str | None = None
    target_lang: str | None = None
    glossary_terms: str = ""
    allow_provider_fallback: bool = False
    audio_duration_seconds: float | None = None
    expected: ExpectedChecks = field(default_factory=ExpectedChecks)

    @property
    def audio_filename(self) -> str:
        return self.audio_path.name


@dataclass(frozen=True)
class EvaluationManifest:
    cases: list[EvaluationCase]
    cost_profiles: dict[str, CostProfile] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    audio_filename: str
    scene: str
    requested_provider: str | None
    target_lang: str | None
    status: str | None
    meeting_id: str | None
    actual_provider: str | None
    checks: list[CheckResult]
    metrics: dict[str, float] = field(default_factory=dict)
    meeting_record_file: str | None = None
    latency_seconds: float | None = None
    audio_duration_seconds: float | None = None
    estimated_asr_cost: float | None = None
    cost_currency: str | None = None
    cost_status: str = "not_configured"

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


def parse_manifest(manifest_path: Path, *, validate_audio_exists: bool = True) -> list[EvaluationCase]:
    return parse_manifest_document(manifest_path, validate_audio_exists=validate_audio_exists).cases


def parse_manifest_document(manifest_path: Path, *, validate_audio_exists: bool = True) -> EvaluationManifest:
    manifest_path = manifest_path.resolve()
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"Manifest file not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest is not valid JSON: {exc}") from exc

    manifest = _as_mapping(raw_manifest, "manifest")
    cost_profiles = _parse_cost_profiles(manifest.get("cost_profiles", {}))
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ManifestError("Manifest must contain a non-empty 'cases' array.")

    default_allow_fallback = bool(manifest.get("allow_provider_fallback", False))
    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        case_data = _as_mapping(raw_case, f"cases[{index}]")
        case_id = _required_str(case_data, "id", f"cases[{index}]")
        if case_id in seen_ids:
            raise ManifestError(f"Duplicate case id: {case_id}")
        seen_ids.add(case_id)

        audio_value = _required_str(case_data, "audio_path", case_id)
        audio_path = _resolve_manifest_path(manifest_path.parent, audio_value)
        if validate_audio_exists and not audio_path.is_file():
            raise ManifestError(f"Audio file for case '{case_id}' does not exist: {audio_path}")

        expected = _parse_expected_checks(case_data.get("expected", {}), case_id)
        providers = _parse_case_providers(case_data, case_id)
        audio_duration_seconds = _resolve_audio_duration_seconds(case_data, case_id, audio_path)
        for provider in providers:
            cases.append(
                EvaluationCase(
                    case_id=case_id,
                    audio_path=audio_path,
                    scene=str(case_data.get("scene", "general") or "general"),
                    provider=provider,
                    target_lang=_optional_str(case_data.get("target_lang")),
                    glossary_terms=_parse_glossary_terms(case_data.get("glossary_terms", "")),
                    allow_provider_fallback=bool(
                        case_data.get("allow_provider_fallback", default_allow_fallback)
                    ),
                    audio_duration_seconds=audio_duration_seconds,
                    expected=expected,
                )
            )
    return EvaluationManifest(cases=cases, cost_profiles=cost_profiles)


def evaluate_meeting_record(case: EvaluationCase, meeting: dict[str, Any]) -> CaseResult:
    expected = case.expected
    checks: list[CheckResult] = []
    metrics: dict[str, float] = {}

    status = _optional_str(meeting.get("status"))
    actual_provider = _optional_str(meeting.get("provider"))
    meeting_id = _optional_str(meeting.get("meeting_id"))
    transcripts = _as_list(meeting.get("transcripts"))
    summary = meeting.get("summary") if isinstance(meeting.get("summary"), dict) else None
    analysis = meeting.get("analysis") if isinstance(meeting.get("analysis"), dict) else None

    checks.append(
        CheckResult(
            "status",
            status == expected.status,
            f"Expected status '{expected.status}', got '{status}'.",
        )
    )

    if case.provider and not case.allow_provider_fallback:
        checks.append(
            CheckResult(
                "provider",
                actual_provider == case.provider,
                f"Expected provider '{case.provider}', got '{actual_provider}'.",
            )
        )

    if expected.min_transcript_count is not None:
        checks.append(
            CheckResult(
                "min_transcript_count",
                len(transcripts) >= expected.min_transcript_count,
                f"Expected at least {expected.min_transcript_count} transcript rows, got {len(transcripts)}.",
                {"actual": len(transcripts), "expected": expected.min_transcript_count},
            )
        )

    combined_text = _collect_meeting_text(meeting)
    for term in expected.required_terms:
        checks.append(
            CheckResult(
                f"required_term:{term}",
                _contains_text(combined_text, term),
                f"Expected output to contain term '{term}'.",
            )
        )
    for term in expected.forbidden_terms:
        checks.append(
            CheckResult(
                f"forbidden_term:{term}",
                not _contains_text(combined_text, term),
                f"Expected output to avoid term '{term}'.",
            )
        )

    speaker_names = {
        str(row.get("speaker", "")).strip()
        for row in transcripts
        if isinstance(row, dict) and str(row.get("speaker", "")).strip()
    }
    speaker_names.discard("Unknown")
    if expected.min_speaker_count is not None:
        checks.append(
            CheckResult(
                "min_speaker_count",
                len(speaker_names) >= expected.min_speaker_count,
                f"Expected at least {expected.min_speaker_count} speakers, got {len(speaker_names)}.",
                {"actual": len(speaker_names), "expected": expected.min_speaker_count},
            )
        )

    if expected.require_final_speakers:
        final_count = sum(
            1
            for row in transcripts
            if isinstance(row, dict) and bool(row.get("speaker_is_final"))
        )
        checks.append(
            CheckResult(
                "final_speakers",
                bool(transcripts) and final_count == len(transcripts),
                f"Expected all transcript rows to have final speaker labels; {final_count}/{len(transcripts)} are final.",
                {"final": final_count, "total": len(transcripts)},
            )
        )

    if expected.require_translations:
        translated_count = sum(
            1
            for row in transcripts
            if isinstance(row, dict)
            and row.get("translated_text")
            and (not case.target_lang or row.get("translated_target_lang") == case.target_lang)
        )
        checks.append(
            CheckResult(
                "translations",
                bool(transcripts) and translated_count == len(transcripts),
                f"Expected translations for all transcript rows; {translated_count}/{len(transcripts)} match target language.",
                {"translated": translated_count, "total": len(transcripts), "target_lang": case.target_lang},
            )
        )

    if expected.require_summary:
        has_summary = bool(summary) and (
            bool(summary.get("overview"))
            or bool(summary.get("key_topics"))
            or bool(summary.get("decisions"))
            or bool(summary.get("risks"))
        )
        checks.append(CheckResult("summary", has_summary, "Expected a non-empty meeting summary."))

    if expected.require_action_items:
        action_items = _as_list(summary.get("action_items") if summary else None)
        actionable_items = [
            item
            for item in action_items
            if isinstance(item, dict) and item.get("is_actionable", True) and item.get("task")
        ]
        checks.append(
            CheckResult(
                "action_items",
                bool(actionable_items),
                f"Expected at least one actionable item, got {len(actionable_items)}.",
                {"actual": len(actionable_items)},
            )
        )

    if expected.require_analysis:
        has_analysis = bool(analysis) and (
            bool(analysis.get("engagement_summary"))
            or bool(_as_list(analysis.get("highlights")))
            or bool(_as_list(analysis.get("participants")))
        )
        checks.append(CheckResult("analysis", has_analysis, "Expected non-empty meeting analysis."))

    hypothesis_transcript = " ".join(
        str(row.get("text", ""))
        for row in transcripts
        if isinstance(row, dict) and row.get("text")
    )
    if expected.reference_transcript is not None and expected.max_wer is not None:
        wer_value = word_error_rate(expected.reference_transcript, hypothesis_transcript)
        metrics["wer"] = wer_value
        checks.append(
            CheckResult(
                "wer",
                wer_value <= expected.max_wer,
                f"Expected WER <= {expected.max_wer:.3f}, got {wer_value:.3f}.",
                {"actual": wer_value, "threshold": expected.max_wer},
            )
        )
    if expected.reference_transcript is not None and expected.max_cer is not None:
        cer_value = character_error_rate(expected.reference_transcript, hypothesis_transcript)
        metrics["cer"] = cer_value
        checks.append(
            CheckResult(
                "cer",
                cer_value <= expected.max_cer,
                f"Expected CER <= {expected.max_cer:.3f}, got {cer_value:.3f}.",
                {"actual": cer_value, "threshold": expected.max_cer},
            )
        )

    return CaseResult(
        case_id=case.case_id,
        audio_filename=case.audio_filename,
        scene=case.scene,
        requested_provider=case.provider,
        target_lang=case.target_lang,
        status=status,
        meeting_id=meeting_id,
        actual_provider=actual_provider,
        checks=checks,
        metrics=metrics,
    )


def word_error_rate(reference: str, hypothesis: str) -> float:
    reference_tokens = re.findall(r"\w+", reference.casefold())
    hypothesis_tokens = re.findall(r"\w+", hypothesis.casefold())
    return _edit_distance_rate(reference_tokens, hypothesis_tokens)


def character_error_rate(reference: str, hypothesis: str) -> float:
    reference_chars = list(re.sub(r"\s+", "", reference.casefold()))
    hypothesis_chars = list(re.sub(r"\s+", "", hypothesis.casefold()))
    return _edit_distance_rate(reference_chars, hypothesis_chars)


def build_json_report(
    results: list[CaseResult],
    *,
    api_base_url: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    passed_count = sum(1 for result in results if result.passed)
    return {
        "generated_at": generated_at.isoformat(),
        "api_base_url": api_base_url,
        "summary": {
            "total": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
        },
        "provider_summary": _build_provider_summary(results),
        "cases": [_case_result_to_json(result) for result in results],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Upload Quality Evaluation Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- API base URL: `{report['api_base_url']}`",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        "",
        "## Provider Comparison",
        "",
        "| Provider | Runs | Passed | Pass rate | Avg WER | Avg CER | Avg latency | Total ASR cost | Cost / passed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for provider in report.get("provider_summary", []):
        lines.append(
            "| "
            f"`{provider['provider']}` | "
            f"{provider['runs']} | "
            f"{provider['passed']} | "
            f"{_format_percent(provider.get('pass_rate'))} | "
            f"{_format_float(provider.get('average_wer'))} | "
            f"{_format_float(provider.get('average_cer'))} | "
            f"{_format_seconds(provider.get('average_latency_seconds'))} | "
            f"{_format_money(provider.get('total_estimated_asr_cost'), provider.get('cost_currency'))} | "
            f"{_format_money(provider.get('cost_per_passed_case'), provider.get('cost_currency'))} |"
        )
    lines.extend(
        [
            "",
        "## Cases",
        "",
        ]
    )
    for case in report["cases"]:
        result_label = "PASS" if case["passed"] else "FAIL"
        provider_label = case["requested_provider"] or "default"
        lines.extend(
            [
                f"### {case['id']} / {provider_label} - {result_label}",
                "",
                f"- Audio: `{case['audio_filename']}`",
                f"- Scene: `{case['scene']}`",
                f"- Provider: `{case['requested_provider'] or 'default'}` -> `{case['actual_provider'] or 'unknown'}`",
                f"- Target language: `{case['target_lang'] or 'none'}`",
                f"- Meeting ID: `{case['meeting_id'] or 'none'}`",
                f"- Status: `{case['status'] or 'unknown'}`",
                f"- Latency: {_format_seconds(case.get('latency_seconds'))}",
                f"- Audio duration: {_format_seconds(case.get('audio_duration_seconds'))}",
                f"- Estimated ASR cost: {_format_money(case.get('estimated_asr_cost'), case.get('cost_currency'))} ({case.get('cost_status', 'not_configured')})",
            ]
        )
        if case.get("metrics"):
            metric_text = ", ".join(f"{key}={value:.3f}" for key, value in case["metrics"].items())
            lines.append(f"- Metrics: {metric_text}")
        if case.get("meeting_record_file"):
            lines.append(f"- Raw meeting record: `{case['meeting_record_file']}`")
        lines.extend(["", "| Check | Result | Message |", "| --- | --- | --- |"])
        for check in case["checks"]:
            lines.append(
                f"| `{check['name']}` | {'PASS' if check['passed'] else 'FAIL'} | {check['message']} |"
            )
        lines.extend(
            [
                "",
                "Manual review:",
                "- Transcript accuracy:",
                "- Speaker labels:",
                "- Glossary usage:",
                "- Translation quality:",
                "- Summary usefulness:",
                "- Follow-up notes:",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_reports(
    results: list[CaseResult],
    *,
    output_dir: Path,
    api_base_url: str,
    generated_at: datetime | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_json_report(results, api_base_url=api_base_url, generated_at=generated_at)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return json_path, markdown_path


def run_case(
    client: httpx.Client,
    case: EvaluationCase,
    *,
    api_base_url: str,
    case_output_dir: Path,
    poll_interval_seconds: float,
    timeout_seconds: float,
    cost_profiles: dict[str, CostProfile] | None = None,
) -> CaseResult:
    upload_url = f"{api_base_url.rstrip('/')}/api/meetings/upload"
    mime_type = mimetypes.guess_type(case.audio_path.name)[0] or "application/octet-stream"
    data = {
        "scene": case.scene,
        "retain_raw_audio": "false",
    }
    if case.provider:
        data["provider"] = case.provider
    if case.target_lang:
        data["target_lang"] = case.target_lang
    if case.glossary_terms:
        data["glossary_terms"] = case.glossary_terms

    started_at = time.monotonic()
    try:
        with case.audio_path.open("rb") as audio_file:
            response = client.post(
                upload_url,
                data=data,
                files={"file": (case.audio_path.name, audio_file, mime_type)},
            )
    except httpx.HTTPError as exc:
        return _case_error_result(
            case,
            "upload_request",
            f"Upload request failed: {exc}",
            latency_seconds=time.monotonic() - started_at,
            cost_profiles=cost_profiles,
        )

    if response.status_code != 202:
        return _case_error_result(
            case,
            "upload_response",
            f"Expected upload HTTP 202, got {response.status_code}: {response.text[:500]}",
            latency_seconds=time.monotonic() - started_at,
            cost_profiles=cost_profiles,
        )

    try:
        initial_record = response.json()
    except ValueError as exc:
        return _case_error_result(
            case,
            "upload_response_json",
            f"Upload response was not valid JSON: {exc}",
            latency_seconds=time.monotonic() - started_at,
            cost_profiles=cost_profiles,
        )

    meeting_id = initial_record.get("meeting_id")
    if not meeting_id:
        return _case_error_result(
            case,
            "meeting_id",
            "Upload response did not include meeting_id.",
            latency_seconds=time.monotonic() - started_at,
            cost_profiles=cost_profiles,
        )

    try:
        meeting = _poll_meeting(
            client,
            api_base_url=api_base_url,
            meeting_id=str(meeting_id),
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        return _case_error_result(
            case,
            "poll_request",
            f"Meeting polling failed: {exc}",
            latency_seconds=time.monotonic() - started_at,
            cost_profiles=cost_profiles,
        )
    except ValueError as exc:
        return _case_error_result(
            case,
            "poll_response_json",
            f"Meeting polling returned invalid JSON: {exc}",
            latency_seconds=time.monotonic() - started_at,
            cost_profiles=cost_profiles,
        )
    latency_seconds = time.monotonic() - started_at
    if meeting is None:
        return _case_error_result(
            case,
            "poll_timeout",
            f"Meeting '{meeting_id}' did not reach a final status within {timeout_seconds:.0f}s.",
            latency_seconds=latency_seconds,
            cost_profiles=cost_profiles,
        )

    case_output_dir.mkdir(parents=True, exist_ok=True)
    record_file_name = f"{_safe_filename(case.case_id)}.{_safe_filename(case.provider or 'default')}.meeting.json"
    record_path = case_output_dir / record_file_name
    record_path.write_text(json.dumps(meeting, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = evaluate_meeting_record(case, meeting)
    cost = _estimate_asr_cost(
        provider=result.actual_provider or result.requested_provider,
        audio_duration_seconds=case.audio_duration_seconds,
        cost_profiles=cost_profiles or {},
    )
    return CaseResult(
        case_id=result.case_id,
        audio_filename=result.audio_filename,
        scene=result.scene,
        requested_provider=result.requested_provider,
        target_lang=result.target_lang,
        status=result.status,
        meeting_id=result.meeting_id,
        actual_provider=result.actual_provider,
        checks=result.checks,
        metrics=result.metrics,
        meeting_record_file=f"cases/{record_file_name}",
        latency_seconds=latency_seconds,
        audio_duration_seconds=case.audio_duration_seconds,
        estimated_asr_cost=cost["amount"],
        cost_currency=cost["currency"],
        cost_status=cost["status"],
    )


def run_evaluation(
    cases: list[EvaluationCase],
    *,
    api_base_url: str,
    output_dir: Path,
    poll_interval_seconds: float,
    timeout_seconds: float,
    cost_profiles: dict[str, CostProfile] | None = None,
) -> tuple[list[CaseResult], Path, Path]:
    run_dir = output_dir / datetime.now(timezone.utc).strftime("upload-quality-%Y%m%d-%H%M%S")
    case_output_dir = run_dir / "cases"
    results: list[CaseResult] = []
    with httpx.Client(timeout=60.0) as client:
        for case in cases:
            results.append(
                run_case(
                    client,
                    case,
                    api_base_url=api_base_url,
                    case_output_dir=case_output_dir,
                    poll_interval_seconds=poll_interval_seconds,
                    timeout_seconds=timeout_seconds,
                    cost_profiles=cost_profiles,
                )
            )
    json_path, markdown_path = write_reports(results, output_dir=run_dir, api_base_url=api_base_url)
    return results, json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate uploaded meeting quality against a private manifest.")
    parser.add_argument("--manifest", required=True, type=Path, help="Path to upload quality manifest JSON.")
    parser.add_argument("--api-base-url", default="http://localhost:8080", help="Running backend base URL.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for local reports.")
    parser.add_argument("--poll-interval-seconds", default=2.0, type=float, help="Meeting polling interval.")
    parser.add_argument("--timeout-seconds", default=600.0, type=float, help="Timeout per case.")
    args = parser.parse_args()

    try:
        manifest = parse_manifest_document(args.manifest)
        results, json_path, markdown_path = run_evaluation(
            manifest.cases,
            api_base_url=args.api_base_url,
            output_dir=args.output_dir,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
            cost_profiles=manifest.cost_profiles,
        )
    except EvaluationError as exc:
        print(f"Evaluation failed: {exc}")
        return 2

    failed_count = sum(1 for result in results if not result.passed)
    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote Markdown report: {markdown_path}")
    print(f"Passed: {len(results) - failed_count}/{len(results)}")
    return 1 if failed_count else 0


def _parse_expected_checks(value: Any, case_id: str) -> ExpectedChecks:
    data = _as_mapping(value, f"{case_id}.expected")
    return ExpectedChecks(
        status=str(data.get("status", "finalized") or "finalized"),
        min_transcript_count=_optional_int(data.get("min_transcript_count"), f"{case_id}.min_transcript_count"),
        required_terms=_str_list(data.get("required_terms", []), f"{case_id}.required_terms"),
        forbidden_terms=_str_list(data.get("forbidden_terms", []), f"{case_id}.forbidden_terms"),
        min_speaker_count=_optional_int(data.get("min_speaker_count"), f"{case_id}.min_speaker_count"),
        require_final_speakers=bool(data.get("require_final_speakers", False)),
        require_translations=bool(data.get("require_translations", False)),
        require_summary=bool(data.get("require_summary", False)),
        require_action_items=bool(data.get("require_action_items", False)),
        require_analysis=bool(data.get("require_analysis", False)),
        reference_transcript=_optional_str(data.get("reference_transcript")),
        max_wer=_optional_float(data.get("max_wer"), f"{case_id}.max_wer"),
        max_cer=_optional_float(data.get("max_cer"), f"{case_id}.max_cer"),
    )


def _parse_case_providers(case_data: dict[str, Any], case_id: str) -> list[str | None]:
    providers_value = case_data.get("providers")
    if providers_value is not None:
        providers = _str_list(providers_value, f"{case_id}.providers")
        normalized = []
        seen: set[str] = set()
        for provider in providers:
            provider_name = provider.strip().lower()
            if not provider_name or provider_name in seen:
                continue
            seen.add(provider_name)
            normalized.append(provider_name)
        if not normalized:
            raise ManifestError(f"{case_id}.providers must contain at least one provider.")
        return normalized

    provider = _optional_str(case_data.get("provider"))
    return [provider.strip().lower() if provider else None]


def _parse_cost_profiles(value: Any) -> dict[str, CostProfile]:
    if value in (None, ""):
        return {}
    profiles_data = _as_mapping(value, "cost_profiles")
    profiles: dict[str, CostProfile] = {}
    for provider, raw_profile in profiles_data.items():
        provider_name = str(provider).strip().lower()
        if not provider_name:
            raise ManifestError("cost_profiles provider names must be non-empty.")
        profile_data = _as_mapping(raw_profile, f"cost_profiles.{provider_name}")
        currency = _required_str(profile_data, "currency", f"cost_profiles.{provider_name}")
        rate = _optional_float(
            profile_data.get("asr_per_audio_minute"),
            f"cost_profiles.{provider_name}.asr_per_audio_minute",
        )
        if rate is None:
            raise ManifestError(f"cost_profiles.{provider_name}.asr_per_audio_minute is required.")
        profiles[provider_name] = CostProfile(
            provider=provider_name,
            currency=currency,
            asr_per_audio_minute=rate,
        )
    return profiles


def _resolve_audio_duration_seconds(
    case_data: dict[str, Any],
    case_id: str,
    audio_path: Path,
) -> float | None:
    configured_duration = _optional_float(
        case_data.get("audio_duration_seconds"),
        f"{case_id}.audio_duration_seconds",
    )
    if configured_duration is not None:
        return configured_duration
    return _read_wav_duration_seconds(audio_path)


def _read_wav_duration_seconds(audio_path: Path) -> float | None:
    if audio_path.suffix.lower() != ".wav" or not audio_path.is_file():
        return None
    with contextlib.suppress(wave.Error, OSError, EOFError):
        with wave.open(str(audio_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return None
            return wav_file.getnframes() / float(frame_rate)
    return None


def _poll_meeting(
    client: httpx.Client,
    *,
    api_base_url: str,
    meeting_id: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    detail_url = f"{api_base_url.rstrip('/')}/api/meetings/{meeting_id}"
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        response = client.get(detail_url)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            last_payload = payload
            if payload.get("status") in FINAL_STATUSES:
                return payload
        time.sleep(poll_interval_seconds)
    return last_payload if last_payload and last_payload.get("status") in FINAL_STATUSES else None


def _case_error_result(
    case: EvaluationCase,
    check_name: str,
    message: str,
    *,
    latency_seconds: float | None = None,
    cost_profiles: dict[str, CostProfile] | None = None,
) -> CaseResult:
    cost = _estimate_asr_cost(
        provider=case.provider,
        audio_duration_seconds=case.audio_duration_seconds,
        cost_profiles=cost_profiles or {},
    )
    return CaseResult(
        case_id=case.case_id,
        audio_filename=case.audio_filename,
        scene=case.scene,
        requested_provider=case.provider,
        target_lang=case.target_lang,
        status=None,
        meeting_id=None,
        actual_provider=None,
        checks=[CheckResult(check_name, False, message)],
        latency_seconds=latency_seconds,
        audio_duration_seconds=case.audio_duration_seconds,
        estimated_asr_cost=cost["amount"],
        cost_currency=cost["currency"],
        cost_status=cost["status"],
    )


def _case_result_to_json(result: CaseResult) -> dict[str, Any]:
    return {
        "id": result.case_id,
        "audio_filename": result.audio_filename,
        "scene": result.scene,
        "requested_provider": result.requested_provider,
        "target_lang": result.target_lang,
        "status": result.status,
        "meeting_id": result.meeting_id,
        "actual_provider": result.actual_provider,
        "passed": result.passed,
        "metrics": result.metrics,
        "meeting_record_file": result.meeting_record_file,
        "latency_seconds": result.latency_seconds,
        "audio_duration_seconds": result.audio_duration_seconds,
        "estimated_asr_cost": result.estimated_asr_cost,
        "cost_currency": result.cost_currency,
        "cost_status": result.cost_status,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "message": check.message,
                "details": check.details,
            }
            for check in result.checks
        ],
    }


def _build_provider_summary(results: list[CaseResult]) -> list[dict[str, Any]]:
    grouped: dict[str, list[CaseResult]] = {}
    for result in results:
        provider = result.actual_provider or result.requested_provider or "default"
        grouped.setdefault(provider, []).append(result)

    summaries: list[dict[str, Any]] = []
    for provider, provider_results in sorted(grouped.items()):
        passed = sum(1 for result in provider_results if result.passed)
        total_costs = [result.estimated_asr_cost for result in provider_results if result.estimated_asr_cost is not None]
        currencies = {
            result.cost_currency
            for result in provider_results
            if result.estimated_asr_cost is not None and result.cost_currency
        }
        total_cost = sum(total_costs) if total_costs else None
        cost_currency = next(iter(currencies)) if len(currencies) == 1 else ("mixed" if len(currencies) > 1 else None)
        summaries.append(
            {
                "provider": provider,
                "runs": len(provider_results),
                "passed": passed,
                "failed": len(provider_results) - passed,
                "pass_rate": passed / len(provider_results) if provider_results else None,
                "average_wer": _average_metric(provider_results, "wer"),
                "average_cer": _average_metric(provider_results, "cer"),
                "average_latency_seconds": _average_value(
                    result.latency_seconds for result in provider_results
                ),
                "total_estimated_asr_cost": total_cost,
                "cost_currency": cost_currency,
                "cost_per_passed_case": total_cost / passed if total_cost is not None and passed else None,
            }
        )
    return summaries


def _average_metric(results: list[CaseResult], metric_name: str) -> float | None:
    return _average_value(result.metrics.get(metric_name) for result in results)


def _average_value(values: Any) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, int | float)]
    if not numeric_values:
        return None
    return sum(numeric_values) / len(numeric_values)


def _estimate_asr_cost(
    *,
    provider: str | None,
    audio_duration_seconds: float | None,
    cost_profiles: dict[str, CostProfile],
) -> dict[str, Any]:
    if audio_duration_seconds is None:
        return {"status": "missing_audio_duration", "amount": None, "currency": None}
    if provider is None:
        return {"status": "not_configured", "amount": None, "currency": None}
    profile = cost_profiles.get(provider.strip().lower())
    if profile is None:
        return {"status": "not_configured", "amount": None, "currency": None}
    return {
        "status": "estimated",
        "amount": round((audio_duration_seconds / 60.0) * profile.asr_per_audio_minute, 6),
        "currency": profile.currency,
    }


def _collect_meeting_text(meeting: dict[str, Any]) -> str:
    values: list[str] = []
    for row in _as_list(meeting.get("transcripts")):
        if isinstance(row, dict):
            values.extend(
                str(row.get(key, ""))
                for key in ("text", "translated_text", "speaker")
                if row.get(key)
            )

    summary = meeting.get("summary")
    if isinstance(summary, dict):
        values.extend(str(summary.get(key, "")) for key in ("title", "overview") if summary.get(key))
        for key in ("key_topics", "decisions", "risks"):
            values.extend(str(item) for item in _as_list(summary.get(key)))
        for item in _as_list(summary.get("action_items")):
            if isinstance(item, dict):
                values.extend(
                    str(item.get(key, ""))
                    for key in ("task", "assignee", "deadline", "source_excerpt")
                    if item.get(key)
                )

    analysis = meeting.get("analysis")
    if isinstance(analysis, dict):
        values.append(str(analysis.get("engagement_summary", "")))
        for item in _as_list(analysis.get("highlights")):
            if isinstance(item, dict):
                values.append(str(item.get("reason", "")))
        for item in _as_list(analysis.get("participants")):
            if isinstance(item, dict):
                values.append(str(item.get("engagement_summary", "")))

    return "\n".join(value for value in values if value)


def _contains_text(haystack: str, needle: str) -> bool:
    return needle.casefold() in haystack.casefold()


def _edit_distance_rate(reference: list[str], hypothesis: list[str]) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    previous = list(range(len(hypothesis) + 1))
    for row_index, ref_item in enumerate(reference, start=1):
        current = [row_index]
        for column_index, hyp_item in enumerate(hypothesis, start=1):
            cost = 0 if ref_item == hyp_item else 1
            current.append(
                min(
                    previous[column_index] + 1,
                    current[column_index - 1] + 1,
                    previous[column_index - 1] + cost,
                )
            )
        previous = current
    return previous[-1] / len(reference)


def _resolve_manifest_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _parse_glossary_terms(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    raise ManifestError("'glossary_terms' must be a string or an array of strings.")


def _as_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{context} must be an object.")
    return value


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _required_str(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{context}.{key} must be a non-empty string.")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def _str_list(value: Any, context: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    raise ManifestError(f"{context} must be a string or an array of strings.")


def _optional_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ManifestError(f"{context} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"{context} must be an integer.") from exc
    if parsed < 0:
        raise ManifestError(f"{context} must be non-negative.")
    return parsed


def _optional_float(value: Any, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ManifestError(f"{context} must be a number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"{context} must be a number.") from exc
    if parsed < 0:
        raise ManifestError(f"{context} must be non-negative.")
    return parsed


def _format_float(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, int | float) else "n/a"


def _format_percent(value: Any) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, int | float) else "n/a"


def _format_seconds(value: Any) -> str:
    return f"{value:.2f}s" if isinstance(value, int | float) else "n/a"


def _format_money(value: Any, currency: Any) -> str:
    if not isinstance(value, int | float):
        return "n/a"
    return f"{value:.4f} {currency}" if currency else f"{value:.4f}"


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "case"


if __name__ == "__main__":
    raise SystemExit(main())
