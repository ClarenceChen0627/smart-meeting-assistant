# Speaker Diarization

Language:
- English: `diarization.md`
- 简体中文: [zh/diarization.md](zh/diarization.md)

Speaker diarization is optional. If it is disabled or unavailable, meetings still run and speaker labels remain provider-provided or `Unknown`.

For detailed Windows diart setup notes, see [diart Setup](diart.md) or [diart Setup 中文版](zh/diart.md).

## Modes

| Mode | Value | Behavior |
| --- | --- | --- |
| Disabled | `DIARIZATION_MODE=disabled` | No backend pyannote/diart processing. Volcengine native speaker clustering can still appear. |
| Offline | `DIARIZATION_MODE=offline` | DashScope transcripts are speaker-confirmed after the meeting ends. |
| Hybrid | `DIARIZATION_MODE=hybrid` | DashScope emits provisional live speaker updates through diart, then final pyannote labels after `finalize`. |

Hybrid mode only applies to DashScope `paraformer-realtime-v1`. Volcengine speaker clustering comes from the provider path.

## Required Variables

```env
DIARIZATION_MODE=offline
HUGGINGFACE_TOKEN=your-hf-token
HF_HOME=models/huggingface
PYANNOTE_CACHE=models/huggingface/hub
HF_HUB_DISABLE_SYMLINKS=1
HF_HUB_OFFLINE=0
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
DIARIZATION_MODEL=pyannote/speaker-diarization-community-1
```

For hybrid mode:

```env
DIARIZATION_MODE=hybrid
REALTIME_DIARIZATION_DURATION_SECONDS=5
REALTIME_DIARIZATION_STEP_SECONDS=0.5
REALTIME_DIARIZATION_LATENCY_SECONDS=1
DIART_SEGMENTATION_MODEL=pyannote/segmentation
DIART_EMBEDDING_MODEL=pyannote/embedding
DIART_PYTHON_PATH=D:\Project\smart-meeting-assistant\backend\.venv-diart\Scripts\python.exe
```

## Optional diart Worker Environment

`diart==0.9.2` requires `numpy<2`, while the main backend pyannote stack can require newer packages. Keep realtime diart in a separate environment:

```powershell
cd backend
.\.venv\Scripts\python.exe -m venv .venv-diart
.\.venv-diart\Scripts\python.exe -m pip install -i https://pypi.org/simple -r requirements-diart.txt
```

Then set `DIART_PYTHON_PATH` to the `.venv-diart` Python executable.

## Windows Cache Notes

- `HF_HOME=models/huggingface` keeps model downloads inside the project.
- `PYANNOTE_CACHE=models/huggingface/hub` lets pyannote reuse the same project-local cache.
- `HF_HUB_DISABLE_SYMLINKS=1` avoids Windows symlink permission failures.
- After all required models are downloaded, set `HF_HUB_OFFLINE=1` to avoid repeated Hugging Face network checks.
- When changing models or downloading for the first time, set `HF_HUB_OFFLINE=0`.

## Limitations

- Hybrid speaker labels are provisional during capture and can jump.
- Final pyannote labels after `finalize` are the authoritative labels for DashScope diarization modes.
- Diarization can be expensive on CPU-only Windows machines.
- Demo mode does not run diarization; it emits fixed speaker labels.
