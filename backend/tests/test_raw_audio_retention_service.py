from __future__ import annotations

from app.core.config import Settings
from app.services.raw_audio_retention_service import RawAudioRetentionService


def build_settings(tmp_path, **overrides) -> Settings:
    return Settings(
        meeting_history_db_path=str(tmp_path / "meeting_history.sqlite3"),
        raw_audio_dir=str(tmp_path / "raw_audio"),
        upload_queue_dir=str(tmp_path / "upload_queue"),
        **overrides,
    )


def test_retain_upload_sanitizes_windows_reserved_filename(tmp_path) -> None:
    service = RawAudioRetentionService(build_settings(tmp_path))

    metadata = service.retain_upload(
        meeting_id="meeting-1",
        audio_data=b"audio",
        filename="CON.wav",
        content_type="audio/wav",
        requested=True,
    )

    assert metadata is not None
    assert metadata.raw_audio_filename == "upload-CON.wav"
    assert (tmp_path / "raw_audio" / "meeting-1" / "upload-CON.wav").read_bytes() == b"audio"


def test_retain_upload_truncates_long_sanitized_filename_and_preserves_extension(tmp_path) -> None:
    service = RawAudioRetentionService(build_settings(tmp_path))
    long_filename = f"{'Launch Plan ' * 20}.wav"

    metadata = service.retain_upload(
        meeting_id="meeting-2",
        audio_data=b"audio",
        filename=long_filename,
        content_type="audio/wav",
        requested=True,
    )

    assert metadata is not None
    assert len(metadata.raw_audio_filename) <= 120
    assert metadata.raw_audio_filename.endswith(".wav")
    assert " " not in metadata.raw_audio_filename


def test_retain_upload_uses_fallback_when_filename_has_no_safe_characters(tmp_path) -> None:
    service = RawAudioRetentionService(build_settings(tmp_path))

    metadata = service.retain_upload(
        meeting_id="meeting-3",
        audio_data=b"audio",
        filename="....",
        content_type="audio/wav",
        requested=True,
    )

    assert metadata is not None
    assert metadata.raw_audio_filename == "upload-audio.bin"


def test_retain_upload_preserves_safe_extension_for_non_ascii_filename(tmp_path) -> None:
    service = RawAudioRetentionService(build_settings(tmp_path))

    metadata = service.retain_upload(
        meeting_id="meeting-4",
        audio_data=b"audio",
        filename="会议录音.wav",
        content_type="audio/wav",
        requested=True,
    )

    assert metadata is not None
    assert metadata.raw_audio_filename == "upload-audio.wav"
