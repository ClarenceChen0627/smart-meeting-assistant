from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.config import Settings


class AudioCodecService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._resolved_ffmpeg_binary: str | None = None

    def resolve_ffmpeg_binary(self) -> str:
        if self._resolved_ffmpeg_binary:
            return self._resolved_ffmpeg_binary

        configured_binary = self._settings.ffmpeg_binary.strip()
        if not configured_binary:
            raise RuntimeError("FFMPEG_BINARY is empty.")

        direct_path = Path(configured_binary)
        if direct_path.exists():
            self._resolved_ffmpeg_binary = str(direct_path)
            return self._resolved_ffmpeg_binary

        resolved_binary = shutil.which(configured_binary)
        if resolved_binary:
            self._resolved_ffmpeg_binary = resolved_binary
            return self._resolved_ffmpeg_binary

        raise RuntimeError(
            "ffmpeg executable not found. Configure FFMPEG_BINARY with an absolute path or add "
            f"ffmpeg to PATH. Current FFMPEG_BINARY={configured_binary!r}"
        )

    async def convert_browser_chunk_to_wav(self, audio_data: bytes) -> bytes:
        return await self._convert_to_wav(audio_data, ".webm")

    async def convert_upload_to_wav(
        self,
        audio_data: bytes,
        *,
        filename: str | None,
        content_type: str | None,
    ) -> bytes:
        suffix = self._infer_suffix(filename, content_type)
        return await self._convert_to_wav(audio_data, suffix)

    async def _convert_to_wav(self, audio_data: bytes, input_suffix: str) -> bytes:
        if not audio_data:
            raise ValueError("Audio payload is empty.")

        input_file = tempfile.NamedTemporaryFile(suffix=input_suffix, delete=False)
        output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            input_file.write(audio_data)
            input_file.flush()
            input_file.close()
            output_file.close()

            completed_process = await asyncio.to_thread(
                self._run_ffmpeg,
                input_file.name,
                output_file.name,
            )
            if completed_process.returncode != 0:
                decoded_stderr = completed_process.stderr.decode(
                    "utf-8",
                    errors="ignore",
                ).replace("\r", "\n")
                stderr_lines = [line.strip() for line in decoded_stderr.splitlines() if line.strip()]
                stderr_excerpt = "\n".join(stderr_lines[-20:]) or "ffmpeg exited without stderr output."
                raise RuntimeError(
                    f"Audio conversion failed: {stderr_excerpt}"
                )

            return Path(output_file.name).read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg is not installed or not on PATH.") from exc
        finally:
            for file_path in (input_file.name, output_file.name):
                try:
                    os.unlink(file_path)
                except FileNotFoundError:
                    pass

    def _run_ffmpeg(self, input_path: str, output_path: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                self.resolve_ffmpeg_binary(),
                "-y",
                "-i",
                input_path,
                "-ac",
                str(self._settings.audio_channels),
                "-ar",
                str(self._settings.sample_rate),
                "-f",
                "wav",
                output_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _infer_suffix(self, filename: str | None, content_type: str | None) -> str:
        if filename:
            suffix = Path(filename).suffix.lower()
            if suffix:
                return suffix

        mapping = {
            "audio/webm": ".webm",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/ogg": ".ogg",
            "audio/opus": ".opus",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
        }
        if content_type:
            return mapping.get(content_type.lower(), ".webm")
        return ".webm"
