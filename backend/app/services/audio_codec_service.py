from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from app.core.config import Settings


class AudioCodecService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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

            process = await asyncio.create_subprocess_exec(
                self._settings.ffmpeg_binary,
                "-y",
                "-i",
                input_file.name,
                "-ac",
                str(self._settings.audio_channels),
                "-ar",
                str(self._settings.sample_rate),
                "-f",
                "wav",
                output_file.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(
                    f"Audio conversion failed: {stderr.decode('utf-8', errors='ignore').strip()}"
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
