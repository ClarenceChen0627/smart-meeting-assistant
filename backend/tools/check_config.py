from __future__ import annotations

import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


VALID_PROVIDERS = {"volcengine", "dashscope", "demo"}
VALID_DIARIZATION_MODES = {"disabled", "offline", "hybrid"}


def _masked(value: str) -> str:
    return "set" if value else "missing"


def _check_path_parent(label: str, path: Path, results: list[tuple[str, str, str]]) -> None:
    parent = path.parent
    if parent.exists():
        writable = parent.is_dir()
        results.append((label, "ok" if writable else "error", str(path)))
        return
    results.append((label, "warn", f"{path} (parent will need to be created: {parent})"))


def build_results() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []

    ffmpeg_binary = settings.ffmpeg_binary
    if Path(ffmpeg_binary).is_absolute():
        ffmpeg_found = Path(ffmpeg_binary).exists()
    else:
        ffmpeg_found = shutil.which(ffmpeg_binary) is not None
    results.append(("ffmpeg", "ok" if ffmpeg_found or settings.demo_mode else "warn", ffmpeg_binary))

    provider_status = "ok" if settings.default_asr_provider in VALID_PROVIDERS else "error"
    results.append(("default ASR provider", provider_status, settings.default_asr_provider))
    results.append(("demo mode", "ok" if settings.demo_mode else "info", str(settings.demo_mode)))
    results.append(("DashScope API key", "ok" if settings.dashscope_api_key else "warn", _masked(settings.dashscope_api_key)))
    results.append(
        (
            "Volcengine ASR keys",
            "ok" if settings.volcengine_asr_configured else "warn",
            f"app_key={_masked(settings.volcengine_asr_app_key)}, access_key={_masked(settings.volcengine_asr_access_key)}",
        )
    )

    diarization_status = "ok" if settings.diarization_mode in VALID_DIARIZATION_MODES else "error"
    results.append(("diarization mode", diarization_status, settings.diarization_mode))
    if settings.diarization_enabled:
        results.append(("Hugging Face token", "ok" if settings.huggingface_token else "warn", _masked(settings.huggingface_token)))
    if settings.realtime_diarization_enabled:
        diart_path = Path(settings.diart_python_path) if settings.diart_python_path else None
        results.append(
            (
                "diart Python",
                "ok" if diart_path and diart_path.exists() else "warn",
                str(diart_path) if diart_path else "missing",
            )
        )

    _check_path_parent("meeting history DB", settings.resolved_meeting_history_db_path, results)
    _check_path_parent("upload queue directory", settings.resolved_upload_queue_dir, results)
    _check_path_parent("raw audio directory", settings.resolved_raw_audio_dir, results)
    results.append(("API token", "ok" if settings.api_access_token else "warn", _masked(settings.api_access_token)))
    results.append(("CORS origins", "ok", ", ".join(settings.cors_allow_origins)))
    results.append(("max upload bytes", "ok", str(settings.max_upload_bytes)))
    results.append(("allowed upload types", "ok", ", ".join(settings.allowed_upload_content_types)))
    return results


def main() -> int:
    results = build_results()
    for label, status, detail in results:
        print(f"[{status.upper()}] {label}: {detail}")
    return 1 if any(status == "error" for _, status, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
