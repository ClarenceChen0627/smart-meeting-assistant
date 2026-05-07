from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
from typing import Any, Protocol

from app.core.config import Settings
from app.services.diarization_service import DiarizationTurn

logger = logging.getLogger(__name__)
WORKER_PATH = Path(__file__).resolve().parents[1] / "workers" / "diart_realtime_worker.py"


class RealtimeDiarizationSession(Protocol):
    async def process_audio(self, audio_chunk: bytes) -> list[DiarizationTurn]: ...

    async def finish(self) -> list[DiarizationTurn]: ...

    async def aclose(self) -> None: ...


class RealtimeDiarizationService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._load_failed = False

    @property
    def is_enabled(self) -> bool:
        return (
            self._settings.realtime_diarization_enabled
            and self._settings.sample_rate == 16000
            and self._settings.audio_channels == 1
        )

    def create_session(self, session_id: str) -> RealtimeDiarizationSession | None:
        if not self.is_enabled:
            if self._settings.realtime_diarization_enabled:
                logger.warning(
                    "Realtime speaker diarization requires 16 kHz mono PCM; got sample_rate=%s channels=%s.",
                    self._settings.sample_rate,
                    self._settings.audio_channels,
                )
            return None
        if self._load_failed:
            return None
        if self._settings.diart_python_path:
            return SubprocessRealtimeDiarizationSession(
                settings=self._settings,
                session_id=session_id,
                mark_load_failed=self._mark_load_failed,
            )
        return DiartRealtimeDiarizationSession(
            settings=self._settings,
            session_id=session_id,
            mark_load_failed=self._mark_load_failed,
        )

    def _mark_load_failed(self) -> None:
        self._load_failed = True


class DiartRealtimeDiarizationSession:
    def __init__(
        self,
        *,
        settings: Settings,
        session_id: str,
        mark_load_failed,
    ) -> None:
        self._settings = settings
        self._session_id = session_id
        self._mark_load_failed = mark_load_failed
        self._pipeline: Any | None = None
        self._numpy: Any | None = None
        self._sliding_window_class: Any | None = None
        self._sliding_window_feature_class: Any | None = None
        self._audio_buffer: Any | None = None
        self._buffer_start_sample = 0
        self._next_window_start_sample = 0
        self._closed = False
        self._failed = False
        self._seen_turns: set[tuple[float, float, str]] = set()
        self._turns: list[DiarizationTurn] = []
        self._process_lock = asyncio.Lock()

        self._duration_samples = max(
            1,
            int(round(settings.realtime_diarization_duration_seconds * settings.sample_rate)),
        )
        self._step_samples = max(
            1,
            int(round(settings.realtime_diarization_step_seconds * settings.sample_rate)),
        )

    async def process_audio(self, audio_chunk: bytes) -> list[DiarizationTurn]:
        if self._closed or self._failed or not audio_chunk:
            return []
        async with self._process_lock:
            if self._closed or self._failed:
                return []
            try:
                await self._ensure_pipeline()
                self._append_audio(audio_chunk)
                return await self._process_ready_windows()
            except Exception as exc:  # pragma: no cover - model/runtime dependent
                self._failed = True
                self._mark_load_failed()
                logger.warning(
                    "Realtime speaker diarization failed for %s; continuing without live speaker updates: %s",
                    self._session_id,
                    exc,
                )
                return []

    async def finish(self) -> list[DiarizationTurn]:
        return []

    async def aclose(self) -> None:
        self._closed = True
        pipeline = self._pipeline
        if pipeline is not None and hasattr(pipeline, "reset"):
            try:
                await asyncio.to_thread(pipeline.reset)
            except Exception:  # pragma: no cover - best effort cleanup
                logger.debug("Realtime diarization reset failed for %s", self._session_id, exc_info=True)

    async def _ensure_pipeline(self) -> None:
        if self._pipeline is not None:
            return
        self._pipeline = await asyncio.to_thread(self._load_pipeline)

    def _load_pipeline(self) -> Any:
        hf_token = self._settings.huggingface_token.strip()
        if hf_token:
            os.environ.setdefault("HF_TOKEN", hf_token)
            os.environ.setdefault("HUGGINGFACE_TOKEN", hf_token)
        os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
        if not os.environ.get("PYANNOTE_CACHE", "").strip():
            hf_home = os.environ.get("HF_HOME", "").strip()
            if hf_home:
                os.environ["PYANNOTE_CACHE"] = str(Path(hf_home) / "hub")

        import numpy as np
        import torch
        import diart.models as diart_models
        from diart import SpeakerDiarization, SpeakerDiarizationConfig
        from pyannote.core import SlidingWindow, SlidingWindowFeature

        device_name = "cuda" if torch.cuda.is_available() else "cpu"
        segmentation = diart_models.SegmentationModel.from_pretrained(
            self._settings.diart_segmentation_model,
            use_hf_token=hf_token or True,
        )
        embedding = diart_models.EmbeddingModel.from_pretrained(
            self._settings.diart_embedding_model,
            use_hf_token=hf_token or True,
        )
        config = SpeakerDiarizationConfig(
            segmentation=segmentation,
            embedding=embedding,
            duration=self._settings.realtime_diarization_duration_seconds,
            step=self._settings.realtime_diarization_step_seconds,
            latency=self._settings.realtime_diarization_latency_seconds,
            sample_rate=self._settings.sample_rate,
            device=torch.device(device_name),
        )

        self._numpy = np
        self._sliding_window_class = SlidingWindow
        self._sliding_window_feature_class = SlidingWindowFeature
        self._audio_buffer = np.empty((0,), dtype=np.float32)
        return SpeakerDiarization(config)

    def _append_audio(self, audio_chunk: bytes) -> None:
        np = self._numpy
        if np is None:
            raise RuntimeError("Realtime diarization pipeline is not initialized.")

        aligned_length = len(audio_chunk) - (len(audio_chunk) % 2)
        if aligned_length <= 0:
            return

        samples = np.frombuffer(audio_chunk[:aligned_length], dtype="<i2").astype(np.float32) / 32768.0
        if self._audio_buffer is None:
            self._audio_buffer = samples
        else:
            self._audio_buffer = np.concatenate((self._audio_buffer, samples))

    async def _process_ready_windows(self) -> list[DiarizationTurn]:
        if self._audio_buffer is None:
            return []

        new_turns: list[DiarizationTurn] = []
        available_end_sample = self._buffer_start_sample + int(self._audio_buffer.shape[0])
        while self._next_window_start_sample + self._duration_samples <= available_end_sample:
            window_start = self._next_window_start_sample
            offset = window_start - self._buffer_start_sample
            window_samples = self._audio_buffer[offset : offset + self._duration_samples]
            feature = self._build_feature(window_samples, window_start)
            output = await asyncio.to_thread(self._pipeline, [feature])
            new_turns.extend(self._extract_new_turns(output))
            self._next_window_start_sample += self._step_samples
            self._trim_buffer()

        return new_turns

    def _build_feature(self, samples, start_sample: int):
        if self._sliding_window_class is None or self._sliding_window_feature_class is None:
            raise RuntimeError("Realtime diarization feature classes are not initialized.")

        sample_rate = self._settings.sample_rate
        return self._sliding_window_feature_class(
            samples.reshape(-1, 1),
            self._sliding_window_class(
                start=start_sample / sample_rate,
                duration=1 / sample_rate,
                step=1 / sample_rate,
            ),
        )

    def _extract_new_turns(self, output: Any) -> list[DiarizationTurn]:
        turns: list[DiarizationTurn] = []
        for item in output or []:
            annotation = item[0] if isinstance(item, tuple) else item
            if not hasattr(annotation, "itertracks"):
                continue
            for turn, _, speaker_label in annotation.itertracks(yield_label=True):
                diarization_turn = DiarizationTurn(
                    start=float(turn.start),
                    end=float(turn.end),
                    speaker_label=str(speaker_label),
                )
                if diarization_turn.end <= diarization_turn.start:
                    continue
                key = (
                    round(diarization_turn.start, 3),
                    round(diarization_turn.end, 3),
                    diarization_turn.speaker_label,
                )
                if key in self._seen_turns:
                    continue
                self._seen_turns.add(key)
                self._turns.append(diarization_turn)
                turns.append(diarization_turn)
        return turns

    def _trim_buffer(self) -> None:
        if self._audio_buffer is None:
            return
        trim_before = self._next_window_start_sample - self._buffer_start_sample
        if trim_before <= 0:
            return
        self._audio_buffer = self._audio_buffer[trim_before:]
        self._buffer_start_sample += trim_before


class SubprocessRealtimeDiarizationSession:
    def __init__(
        self,
        *,
        settings: Settings,
        session_id: str,
        mark_load_failed,
    ) -> None:
        self._settings = settings
        self._session_id = session_id
        self._mark_load_failed = mark_load_failed
        self._process: subprocess.Popen[bytes] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._closed = False
        self._failed = False
        self._lock = asyncio.Lock()

    async def process_audio(self, audio_chunk: bytes) -> list[DiarizationTurn]:
        if self._closed or self._failed or not audio_chunk:
            return []
        async with self._lock:
            try:
                response = await asyncio.to_thread(
                    self._process_audio_sync,
                    audio_chunk,
                )
            except Exception as exc:  # pragma: no cover - process/runtime dependent
                self._failed = True
                self._mark_load_failed()
                message = str(exc) or repr(exc) or exc.__class__.__name__
                logger.warning(
                    "Realtime speaker diarization worker failed for %s; continuing without live speaker updates: %s: %s",
                    self._session_id,
                    exc.__class__.__name__,
                    message,
                )
                await self.aclose()
                return []
        return self._parse_turns(response)

    async def finish(self) -> list[DiarizationTurn]:
        if self._closed or self._failed or self._process is None:
            return []
        async with self._lock:
            try:
                response = await asyncio.to_thread(self._finish_sync)
            except Exception:  # pragma: no cover - best effort finalize
                logger.debug("Realtime diarization worker finish failed for %s", self._session_id, exc_info=True)
                return []
        return self._parse_turns(response)

    async def aclose(self) -> None:
        self._closed = True
        await asyncio.to_thread(self._close_sync)

    def _process_audio_sync(self, audio_chunk: bytes) -> dict[str, Any]:
        self._ensure_process_sync()
        return self._send_request_sync(
            {
                "type": "audio",
                "payload": base64.b64encode(audio_chunk).decode("ascii"),
            }
        )

    def _finish_sync(self) -> dict[str, Any]:
        return self._send_request_sync({"type": "finish"})

    def _ensure_process_sync(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        if not WORKER_PATH.exists():
            raise RuntimeError(f"Diart worker script is missing: {WORKER_PATH}")

        python_path = self._settings.diart_python_path
        self._process = subprocess.Popen(
            [python_path, str(WORKER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stderr_thread = threading.Thread(
            target=self._log_stderr_sync,
            args=(self._process,),
            name=f"diart-worker-stderr-{self._session_id}",
            daemon=True,
        )
        self._stderr_thread.start()
        self._send_request_sync(
            {
                "type": "init",
                "session_id": self._session_id,
                "settings": {
                    "sample_rate": self._settings.sample_rate,
                    "duration": self._settings.realtime_diarization_duration_seconds,
                    "step": self._settings.realtime_diarization_step_seconds,
                    "latency": self._settings.realtime_diarization_latency_seconds,
                    "segmentation_model": self._settings.diart_segmentation_model,
                    "embedding_model": self._settings.diart_embedding_model,
                    "huggingface_token": self._settings.huggingface_token,
                },
            }
        )

    def _send_request_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("Realtime diarization worker is not running.")
        returncode = self._process.poll()
        if returncode is not None:
            raise RuntimeError(f"Realtime diarization worker exited with code {returncode}.")

        self._process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        self._process.stdin.flush()
        raw_response = self._process.stdout.readline()
        if not raw_response:
            raise RuntimeError("Realtime diarization worker closed stdout.")
        response = json.loads(raw_response.decode("utf-8"))
        if response.get("error"):
            traceback_text = response.get("traceback")
            if traceback_text:
                logger.warning(
                    "Realtime diarization worker traceback for %s:\n%s",
                    self._session_id,
                    traceback_text,
                )
            raise RuntimeError(str(response["error"]))
        return response

    def _close_sync(self) -> None:
        process = self._process
        self._process = None
        if process is not None:
            try:
                if process.stdin is not None and process.poll() is None:
                    process.stdin.write((json.dumps({"type": "close"}) + "\n").encode("utf-8"))
                    process.stdin.flush()
            except Exception:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        stderr_thread = self._stderr_thread
        self._stderr_thread = None
        if stderr_thread is not None and stderr_thread.is_alive():
            stderr_thread.join(timeout=1)

    def _log_stderr_sync(self, process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return
        while True:
            line = process.stderr.readline()
            if not line:
                break
            logger.warning(
                "Realtime diarization worker stderr for %s: %s",
                self._session_id,
                line.decode("utf-8", errors="replace").strip(),
            )

    def _parse_turns(self, response: dict[str, Any]) -> list[DiarizationTurn]:
        turns: list[DiarizationTurn] = []
        for item in response.get("turns") or []:
            turns.append(
                DiarizationTurn(
                    start=float(item["start"]),
                    end=float(item["end"]),
                    speaker_label=str(item["speaker_label"]),
                )
            )
        return turns
