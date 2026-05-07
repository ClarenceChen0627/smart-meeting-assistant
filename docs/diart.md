# diart Realtime Speaker Diarization

Language:
- English: `diart.md`
- 简体中文: [zh/diart.md](zh/diart.md)

This page is the English overview for realtime diart setup. The full Windows step-by-step guide is currently maintained in Chinese at [zh/diart.md](zh/diart.md).

## When diart Runs

diart is only used for provisional live speaker updates in hybrid diarization mode. It starts lazily when a live meeting session begins and all of these conditions are true:

```env
DEFAULT_ASR_PROVIDER=dashscope
DASHSCOPE_ASR_MODEL=paraformer-realtime-v1
DIARIZATION_MODE=hybrid
DIART_PYTHON_PATH=D:\Project\smart-meeting-assistant\backend\.venv-diart\Scripts\python.exe
```

The main FastAPI backend still runs in `backend\.venv`. The diart worker should run in a separate `backend\.venv-diart` environment because `diart==0.9.2` and the main pyannote stack can require incompatible NumPy versions.

## Setup Summary

1. Install the main backend dependencies in `backend\.venv`.
2. Create `backend\.venv-diart` from the main backend Python executable.
3. Install `requirements-diart.txt` into `backend\.venv-diart`.
4. Configure `DIART_PYTHON_PATH`.
5. Pre-download or cache Hugging Face models if you want offline startup.
6. Start FastAPI and choose DashScope + hybrid diarization.

## Related Docs

- [Speaker Diarization](diarization.md)
- [Configuration](configuration.md)
- [中文 diart 详细启动说明](zh/diart.md)
