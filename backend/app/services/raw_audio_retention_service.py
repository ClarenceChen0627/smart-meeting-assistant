from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings
from app.schemas.meeting_history import RawAudioMetadata


class RawAudioRetentionService:
    _FALLBACK_FILENAME = "upload-audio.bin"
    _MAX_FILENAME_LENGTH = 120
    _WINDOWS_RESERVED_NAMES = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._root = settings.resolved_raw_audio_dir

    def retain_upload(
        self,
        *,
        meeting_id: str,
        audio_data: bytes,
        filename: str | None,
        content_type: str | None,
        requested: bool,
    ) -> RawAudioMetadata | None:
        if not requested or not self._settings.raw_audio_retention_enabled:
            return None
        if not audio_data:
            return None

        safe_filename = self._sanitize_filename(filename)
        target_dir = self._root / meeting_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_filename
        target_path.write_bytes(audio_data)
        return RawAudioMetadata(
            raw_audio_retained=True,
            raw_audio_path=str(target_path),
            raw_audio_filename=safe_filename,
            raw_audio_content_type=content_type,
            raw_audio_size_bytes=len(audio_data),
        )

    @staticmethod
    def _sanitize_filename(filename: str | None) -> str:
        source = Path(filename or RawAudioRetentionService._FALLBACK_FILENAME).name
        source_path = Path(source)
        raw_suffix = source_path.suffix
        safe_suffix = ""
        if raw_suffix:
            normalized_suffix = re.sub(r"[^A-Za-z0-9.]+", "", raw_suffix)
            if normalized_suffix.startswith(".") and re.search(r"[A-Za-z0-9]", normalized_suffix):
                safe_suffix = normalized_suffix[:16]

        raw_stem = source_path.stem if raw_suffix else source
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_stem).strip("._-")
        if not safe_stem:
            fallback_path = Path(RawAudioRetentionService._FALLBACK_FILENAME)
            safe_stem = fallback_path.stem
            if not safe_suffix:
                safe_suffix = fallback_path.suffix

        safe = f"{safe_stem}{safe_suffix}"

        safe_path = Path(safe)
        if safe_path.stem.upper() in RawAudioRetentionService._WINDOWS_RESERVED_NAMES:
            safe = f"upload-{safe}"

        if len(safe) <= RawAudioRetentionService._MAX_FILENAME_LENGTH:
            return safe

        safe_path = Path(safe)
        suffix = safe_path.suffix if len(safe_path.suffix) <= 16 else ""
        stem = safe_path.stem if suffix else safe
        stem_limit = max(1, RawAudioRetentionService._MAX_FILENAME_LENGTH - len(suffix))
        return f"{stem[:stem_limit]}{suffix}"
