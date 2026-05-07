from __future__ import annotations

import base64
from contextlib import redirect_stdout
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROTOCOL_STDOUT = sys.stdout


@dataclass(frozen=True)
class WorkerTurn:
    start: float
    end: float
    speaker_label: str


class DiartWorker:
    def __init__(self) -> None:
        self._pipeline: Any | None = None
        self._numpy: Any | None = None
        self._sliding_window_class: Any | None = None
        self._sliding_window_feature_class: Any | None = None
        self._audio_buffer: Any | None = None
        self._buffer_start_sample = 0
        self._next_window_start_sample = 0
        self._duration_samples = 0
        self._step_samples = 0
        self._sample_rate = 16000
        self._seen_turns: set[tuple[float, float, str]] = set()

    def init(self, settings: dict[str, Any]) -> None:
        hf_token = str(settings.get("huggingface_token") or "").strip()
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

        self._sample_rate = int(settings["sample_rate"])
        duration = float(settings["duration"])
        step = float(settings["step"])
        latency = float(settings["latency"])
        self._duration_samples = max(1, int(round(duration * self._sample_rate)))
        self._step_samples = max(1, int(round(step * self._sample_rate)))

        device_name = "cuda" if torch.cuda.is_available() else "cpu"
        segmentation = diart_models.SegmentationModel.from_pretrained(
            str(settings["segmentation_model"]),
            use_hf_token=hf_token or True,
        )
        embedding = diart_models.EmbeddingModel.from_pretrained(
            str(settings["embedding_model"]),
            use_hf_token=hf_token or True,
        )
        config = SpeakerDiarizationConfig(
            segmentation=segmentation,
            embedding=embedding,
            duration=duration,
            step=step,
            latency=latency,
            sample_rate=self._sample_rate,
            device=torch.device(device_name),
        )
        self._numpy = np
        self._sliding_window_class = SlidingWindow
        self._sliding_window_feature_class = SlidingWindowFeature
        self._audio_buffer = np.empty((0,), dtype=np.float32)
        self._pipeline = SpeakerDiarization(config)

    def process_audio(self, payload: str) -> list[WorkerTurn]:
        if self._pipeline is None:
            raise RuntimeError("Worker is not initialized.")
        audio_chunk = base64.b64decode(payload)
        self._append_audio(audio_chunk)
        return self._process_ready_windows()

    def finish(self) -> list[WorkerTurn]:
        return []

    def close(self) -> None:
        if self._pipeline is not None and hasattr(self._pipeline, "reset"):
            self._pipeline.reset()

    def _append_audio(self, audio_chunk: bytes) -> None:
        np = self._numpy
        if np is None:
            raise RuntimeError("Numpy is not initialized.")
        aligned_length = len(audio_chunk) - (len(audio_chunk) % 2)
        if aligned_length <= 0:
            return
        samples = np.frombuffer(audio_chunk[:aligned_length], dtype="<i2").astype(np.float32) / 32768.0
        self._audio_buffer = np.concatenate((self._audio_buffer, samples))

    def _process_ready_windows(self) -> list[WorkerTurn]:
        if self._audio_buffer is None:
            return []

        turns: list[WorkerTurn] = []
        available_end_sample = self._buffer_start_sample + int(self._audio_buffer.shape[0])
        while self._next_window_start_sample + self._duration_samples <= available_end_sample:
            window_start = self._next_window_start_sample
            offset = window_start - self._buffer_start_sample
            samples = self._audio_buffer[offset : offset + self._duration_samples]
            feature = self._build_feature(samples, window_start)
            output = self._pipeline([feature])
            turns.extend(self._extract_new_turns(output))
            self._next_window_start_sample += self._step_samples
            self._trim_buffer()
        return turns

    def _build_feature(self, samples, start_sample: int):
        if self._sliding_window_class is None or self._sliding_window_feature_class is None:
            raise RuntimeError("Pyannote feature classes are not initialized.")
        return self._sliding_window_feature_class(
            samples.reshape(-1, 1),
            self._sliding_window_class(
                start=start_sample / self._sample_rate,
                duration=1 / self._sample_rate,
                step=1 / self._sample_rate,
            ),
        )

    def _extract_new_turns(self, output: Any) -> list[WorkerTurn]:
        turns: list[WorkerTurn] = []
        for item in output or []:
            annotation = item[0] if isinstance(item, tuple) else item
            if not hasattr(annotation, "itertracks"):
                continue
            for turn, _, speaker_label in annotation.itertracks(yield_label=True):
                worker_turn = WorkerTurn(
                    start=float(turn.start),
                    end=float(turn.end),
                    speaker_label=str(speaker_label),
                )
                if worker_turn.end <= worker_turn.start:
                    continue
                key = (
                    round(worker_turn.start, 3),
                    round(worker_turn.end, 3),
                    worker_turn.speaker_label,
                )
                if key in self._seen_turns:
                    continue
                self._seen_turns.add(key)
                turns.append(worker_turn)
        return turns

    def _trim_buffer(self) -> None:
        if self._audio_buffer is None:
            return
        trim_before = self._next_window_start_sample - self._buffer_start_sample
        if trim_before <= 0:
            return
        self._audio_buffer = self._audio_buffer[trim_before:]
        self._buffer_start_sample += trim_before


def _write_response(payload: dict[str, Any]) -> None:
    PROTOCOL_STDOUT.write(json.dumps(payload) + "\n")
    PROTOCOL_STDOUT.flush()


def _serialize_turns(turns: list[WorkerTurn]) -> list[dict[str, Any]]:
    return [
        {
            "start": turn.start,
            "end": turn.end,
            "speaker_label": turn.speaker_label,
        }
        for turn in turns
    ]


def main() -> None:
    worker = DiartWorker()
    for raw_line in sys.stdin:
        try:
            message = json.loads(raw_line)
            message_type = message.get("type")
            if message_type == "init":
                with redirect_stdout(sys.stderr):
                    worker.init(message["settings"])
                _write_response({"turns": []})
            elif message_type == "audio":
                with redirect_stdout(sys.stderr):
                    turns = worker.process_audio(message["payload"])
                _write_response({"turns": _serialize_turns(turns)})
            elif message_type == "finish":
                with redirect_stdout(sys.stderr):
                    turns = worker.finish()
                _write_response({"turns": _serialize_turns(turns)})
            elif message_type == "close":
                with redirect_stdout(sys.stderr):
                    worker.close()
                _write_response({"turns": []})
                break
            else:
                _write_response({"error": f"Unsupported message type: {message_type}"})
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {str(exc) or repr(exc)}"
            _write_response({"error": error, "traceback": traceback.format_exc()})


if __name__ == "__main__":
    main()
