# Configuration

Language:
- English: `configuration.md`
- 简体中文: [zh/configuration.md](zh/configuration.md)

Copy the root backend environment file before local development:

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

Frontend-only URL overrides belong in `frontend/.env.local`, copied from `frontend/.env.example`.

## Minimal Configuration Matrix

| Workflow | Required backend variables | Notes |
| --- | --- | --- |
| Demo mode | `DEMO_MODE=1` | No external AI keys required. Use for local smoke tests and CI only. |
| Browser frontend | `VITE_API_BASE_URL`, `VITE_WS_BASE_URL` only when backend is not `localhost:8080` | Store these in `frontend/.env.local`. |
| Local backend | `PORT`, `LOG_LEVEL`, `MEETING_HISTORY_DB_PATH` | Defaults are enough for a backend boot. |
| Private self-hosting | `API_ACCESS_TOKEN`, `CORS_ALLOW_ORIGINS`, `MAX_UPLOAD_BYTES` | Keep token empty only for local development. Use HTTPS in production. |
| Realtime Volcengine ASR | `DEFAULT_ASR_PROVIDER=volcengine`, `VOLCENGINE_ASR_APP_KEY`, `VOLCENGINE_ASR_ACCESS_KEY`, `VOLCENGINE_ASR_RESOURCE_ID` | Volcengine can return native speaker clustering. |
| Realtime DashScope ASR | `DEFAULT_ASR_PROVIDER=dashscope`, `DASHSCOPE_API_KEY`, `DASHSCOPE_ASR_MODEL` | Required for DashScope Paraformer realtime ASR. |
| Translation, summary, analysis | `DASHSCOPE_API_KEY`, `DASHSCOPE_MODEL`, `DASHSCOPE_TRANSLATION_MODEL` | Used by translation, summary, and meeting analysis. |
| Upload meetings | A configured ASR provider plus `FFMPEG_BINARY` | `DEMO_MODE=1` skips external ASR and ffmpeg conversion for demo uploads. |
| Offline diarization | DashScope ASR plus `DIARIZATION_MODE=offline`, `HUGGINGFACE_TOKEN`, `DIARIZATION_MODEL` | Runs after `finalize` or upload transcription. |
| Hybrid diarization | DashScope ASR plus `DIARIZATION_MODE=hybrid`, `DIART_PYTHON_PATH` | Live diart updates are provisional; final pyannote output is authoritative. |
| Electron client | Running backend plus `frontend/.env.local` if backend URL is custom | Electron wraps the Vite frontend and does not start FastAPI. |

## Demo Mode

Set:

```env
DEMO_MODE=1
DEFAULT_ASR_PROVIDER=demo
DIARIZATION_MODE=disabled
```

Demo mode provides deterministic local ASR, translation, summary, and analysis. It is intended for onboarding, development, documentation smoke tests, and CI. It does not represent real model quality.

When `DEMO_MODE=1`, `provider=demo` is available on both WebSocket and upload workflows. If real ASR credentials are missing and the frontend still requests `volcengine` or `dashscope`, the backend can fall back to the configured demo provider. When `DEMO_MODE=0`, an explicit `provider=demo` request stays on the demo provider and reports that it is not configured instead of silently using a real provider.

Run the fast demo smoke suite when you only need to verify the local demo path:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -m smoke
```

```bash
cd backend
./.venv/Scripts/python.exe -m pytest -m smoke
```

## Backend Variables

- `PORT`: FastAPI port, default `8080`.
- `LOG_LEVEL`: backend logging level, default `INFO`.
- `DEMO_MODE`: enables deterministic local demo providers when set to `1`, `true`, `yes`, or `on`.
- `API_ACCESS_TOKEN`: optional self-hosted access token. When set, protected HTTP APIs require `Authorization: Bearer <token>` or `X-API-Token`; `/ws/meeting` requires `access_token=<token>`.
- `CORS_ALLOW_ORIGINS`: comma-separated allowed browser origins. Defaults to `*` for local development; use explicit HTTPS origins in production.
- `MAX_UPLOAD_BYTES`: maximum accepted upload size for meeting uploads and transcript utility endpoints.
- `ALLOWED_UPLOAD_CONTENT_TYPES`: comma-separated accepted upload content types. Use `*` only for trusted local development.
- `FFMPEG_BINARY`: ffmpeg executable used for non-demo uploads.
- `AUDIO_SAMPLE_RATE`: PCM sample rate, default `16000`.
- `AUDIO_CHANNELS`: audio channels, default `1`.
- `MEETING_HISTORY_DB_PATH`: SQLite meeting history path.
- `RAW_AUDIO_RETENTION_ENABLED`: allows user-requested raw upload retention, default `true`.
- `RAW_AUDIO_DIR`: retained upload audio directory, default `data/raw_audio`.
- `UPLOAD_QUEUE_DIR`: temporary persistent upload queue payload directory, default `data/upload_queue`.
- `UPLOAD_QUEUE_EMBEDDED_WORKER_ENABLED`: starts an in-process upload queue worker with FastAPI by default. Set to `0` when running a separate worker with `tools/run_upload_worker.py`.
- `UPLOAD_QUEUE_MAX_ATTEMPTS`: maximum queue-level attempts per upload job, default `3`.
- `UPLOAD_QUEUE_RETRY_BASE_SECONDS`: base delay for queue-level exponential backoff, default `30`.
- `UPLOAD_QUEUE_RETRY_MAX_SECONDS`: maximum queue-level retry delay, default `300`.
- `UPLOAD_QUEUE_PROCESSING_TIMEOUT_SECONDS`: stale processing claim timeout used during startup recovery, default `1800`.
- `CUSTOM_GLOSSARY_TERMS`: optional environment default glossary. Saved terms from `/api/glossary/terms` and per-meeting terms are merged before this fallback list. Use one term per line or `term=>replacement`.
- `DEFAULT_ASR_PROVIDER`: `volcengine`, `dashscope`, or `demo`.
- `DASHSCOPE_API_KEY`: DashScope key for ASR, translation, summary, and analysis.
- `DASHSCOPE_MODEL`: chat model for summary and analysis.
- `DASHSCOPE_TRANSLATION_MODEL`: translation model.
- `DASHSCOPE_ASR_MODEL`: realtime ASR model, usually `paraformer-realtime-v1`.
- `DASHSCOPE_ASR_WS_URL`: DashScope ASR websocket endpoint.
- `DASHSCOPE_WORKSPACE_ID`: optional DashScope workspace.
- `VOLCENGINE_ASR_APP_KEY`: Volcengine speech app key.
- `VOLCENGINE_ASR_ACCESS_KEY`: Volcengine speech access key.
- `VOLCENGINE_ASR_RESOURCE_ID`: Volcengine speech resource ID.
- `VOLCENGINE_ASR_WS_URL`: Volcengine streaming endpoint.
- `VOLCENGINE_ASR_NOSTREAM_WS_URL`: Volcengine upload transcription endpoint.
- `VOLCENGINE_ASR_SSD_VERSION`: Volcengine speaker clustering SSD version.

## Frontend Variables

Store these in `frontend/.env.local`:

```env
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
```

Do not put backend secrets in frontend environment files.

## Windows Backend Commands

Backend Python commands must use the repository virtual environment:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe tools\check_config.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
.\.venv\Scripts\python.exe tools\run_upload_worker.py --once
```

`--once` processes only jobs that are eligible at command start. Jobs delayed by `UPLOAD_QUEUE_RETRY_BASE_SECONDS` / `UPLOAD_QUEUE_RETRY_MAX_SECONDS` remain queued until their `next_run_at`.

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe tools/check_config.py
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
./.venv/Scripts/python.exe tools/run_upload_worker.py --once
```
