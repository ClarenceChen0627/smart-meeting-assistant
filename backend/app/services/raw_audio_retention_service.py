from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings
from app.schemas.meeting_history import RawAudioMetadata


class RawAudioRetentionService:
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
        source = Path(filename or "upload-audio.bin").name
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", source).strip("._")
        return safe or "upload-audio.bin"
