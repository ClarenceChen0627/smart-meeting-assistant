# Smart Meeting Assistant

Language:
- English: `README.md`
- 简体中文: [README-zh.md](README-zh.md)

Smart Meeting Assistant is a meeting copilot built with React 18 and FastAPI. It supports live speech transcription, live transcript translation, meeting summarization, action-item extraction, and meeting sentiment / engagement analysis over a WebSocket-based realtime workflow. The frontend can run in a browser or as a Windows-first Electron desktop client.

## Architecture

- `frontend`: React 18 + TypeScript + Vite + Tailwind CSS
- `backend`: FastAPI + Uvicorn
- `frontend/electron`: Electron desktop shell for the Vite frontend

## Features

### Realtime pipeline

- Browser microphone capture
- Switchable live ASR providers:
  - Volcengine Doubao ASR (default)
  - DashScope Paraformer (`paraformer-realtime-v1`)
- Realtime transcript rendering with speaker labels from the active provider or diarization mode
- DashScope speaker diarization can run in `offline` mode after `finalize`, or in `hybrid` mode with provisional live diart updates followed by final pyannote confirmation
- Real-time transcript translation to a target language, currently supporting 10 languages including:
  - English, Spanish, French, German, Chinese
  - Japanese, Korean, Portuguese, Arabic, Hindi

### Meeting summary

- Final summary after recording stops
- Structured output:
  - `title`
  - `overview`
  - `key_topics`
  - `decisions`
  - `action_items`
  - `risks`
- Generated meeting titles can be renamed by the user
- Summary content can be edited after generation, including overview, topics, decisions, risks, and action item details

### Meeting analysis

- Incremental meeting sentiment / engagement analysis during the session
- Final meeting analysis after `finalize`
- Structured output:
  - `overall_sentiment`
  - `engagement_level`
  - `engagement_summary`
  - signal counts for:
    - `agreement`
    - `disagreement`
    - `tension`
    - `hesitation`
- Transcript-level highlight markers for emotionally significant moments

### Frontend UX

- Top-level `Live` / `Upload` mode switch that reuses the same result workspace
- Resizable sidebar and transcript workspace on desktop
- Scrollable transcript list
- Bilingual transcript cards
- Separate Meeting Summary and Meeting Analysis panels
- In-app meeting history drawer with saved record selection and deletion
- Saved meeting titles can be renamed
- Action item completion status can be updated from current or historical meetings
- Generated summaries can be corrected from the Summary panel
- Optional Windows portable Electron desktop client

### Meeting history

- SQLite-backed meeting history persistence
- Each websocket meeting session is saved as a `draft` immediately after connection
- Uploaded meetings are saved as `processing`, then transition to `finalized` or `failed`
- History records are labeled with `source_type` (`live` or `upload`)
- Live transcript, uploaded transcript, transcript translations, meeting analysis, and final summary are stored for later review
- Saved meetings can be reopened from the frontend, regardless of whether they came from live capture or upload
- Meeting titles, summary fields, and action item status/content can be edited and persisted
- Unneeded meeting records can be permanently deleted from the history panel

### Upload meeting mode

- Upload one meeting audio file from the frontend `Upload` mode
- The backend creates a persisted upload meeting record immediately and processes it asynchronously
- Transcript appears first, then translations / analysis / summary are filled in incrementally
- Upload results reuse the same `Transcript`, `Summary`, `Action Items`, and `Analysis` panels as live meetings
- `POST /api/meetings/upload` is the product-facing upload workflow
- `POST /api/transcribe` and `POST /api/transcribe/batch` remain transcript-only utility/debug endpoints

## Project Structure

```text
smart-meeting-assistant/
├─ frontend/
├─ backend/
├─ .env.example
├─ docker-compose.yml
├─ FULL_FEATURE_TEST_SCRIPT.md
└─ README.md
```

## Tech Stack

### Frontend

- React 18
- TypeScript
- Vite
- Tailwind CSS
- Radix UI
- WebSocket
- Web Audio API

### Backend

- FastAPI
- Uvicorn
- Pydantic
- httpx
- websockets
- python-dotenv
- ffmpeg

### External services

- DashScope Paraformer Realtime ASR
- DashScope Qwen-MT
- DashScope / Qwen chat models

## Current Workflow

1. The browser captures microphone audio.
2. The frontend converts audio into PCM frames and streams them to the backend over WebSocket.
3. The backend creates a persisted `draft` meeting record and emits `session_started`.
4. The backend forwards audio to the selected realtime ASR provider.
5. The backend emits `transcript` messages and persists the latest transcript state.
6. The backend translates transcript text and emits `translation` messages.
7. The backend periodically analyzes emotional dynamics, emits `analysis`, and stores the latest analysis snapshot.
8. When recording stops, the frontend sends `finalize`.
9. The backend closes the session WAV, runs final pyannote speaker confirmation when diarization is enabled, emits final `speaker_update` messages, sends the final `analysis`, sends the final `summary`, marks the meeting as `finalized`, then closes the socket. In `hybrid` mode, provisional diart speaker updates may also be emitted during live capture.

## Upload Workflow

1. The user switches the frontend into `Upload` mode and selects one audio file.
2. The frontend submits `POST /api/meetings/upload` with the file, `scene`, `target_lang`, and `provider`.
3. The backend creates a persisted meeting record with `source_type=upload`, `status=processing`, and `processing_stage=transcribing`.
4. The backend converts the uploaded file to WAV with `ffmpeg`, runs ASR, and persists transcript rows.
5. If translation is enabled, the backend translates each transcript row and persists the translated text.
6. The backend generates meeting analysis, then the final summary / action items, updating the same meeting record.
7. The frontend polls `GET /api/meetings/{meeting_id}` every few seconds and progressively renders transcript first, then analysis and summary.
8. The upload meeting record is marked `finalized` on success or `failed` on unrecoverable processing errors.

## Requirements

- Node.js 18+
- Python 3.10+
- ffmpeg
- A valid DashScope API key
- Optional: a Hugging Face access token for offline or hybrid speaker diarization

## Environment Variables

Create `.env` in the project root:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Recommended backend configuration:

```bash
DASHSCOPE_API_KEY=your-dashscope-api-key
DASHSCOPE_MODEL=qwen-plus
DASHSCOPE_ASR_MODEL=paraformer-realtime-v1
DASHSCOPE_TRANSLATION_MODEL=qwen-mt-flash
DEFAULT_ASR_PROVIDER=volcengine
VOLCENGINE_ASR_APP_KEY=your-volcengine-app-key
VOLCENGINE_ASR_ACCESS_KEY=your-volcengine-access-key
VOLCENGINE_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
VOLCENGINE_ASR_WS_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
VOLCENGINE_ASR_NOSTREAM_WS_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream
VOLCENGINE_ASR_SSD_VERSION=200
DIARIZATION_MODE=disabled
HUGGINGFACE_TOKEN=
HF_HOME=models/huggingface
PYANNOTE_CACHE=models/huggingface/hub
HF_HUB_DISABLE_SYMLINKS=1
HF_HUB_OFFLINE=0
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
DIARIZATION_MODEL=pyannote/speaker-diarization-community-1
REALTIME_DIARIZATION_DURATION_SECONDS=5
REALTIME_DIARIZATION_STEP_SECONDS=0.5
REALTIME_DIARIZATION_LATENCY_SECONDS=1
DIART_SEGMENTATION_MODEL=pyannote/segmentation
DIART_EMBEDDING_MODEL=pyannote/embedding
DIART_PYTHON_PATH=

PORT=8080
LOG_LEVEL=INFO
FFMPEG_BINARY=ffmpeg
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
MEETING_HISTORY_DB_PATH=data/meeting_history.sqlite3
```

### Important variables

- `DASHSCOPE_API_KEY`: used by ASR, translation, summary, and meeting analysis
- `DASHSCOPE_MODEL`: used by summary and meeting analysis
- `DASHSCOPE_ASR_MODEL`: realtime ASR model
- `DASHSCOPE_TRANSLATION_MODEL`: transcript translation model
- `DEFAULT_ASR_PROVIDER`: default ASR provider (`volcengine` or `dashscope`)
- `VOLCENGINE_ASR_APP_KEY`: Volcengine speech APP ID used by `X-Api-App-Key`
- `VOLCENGINE_ASR_ACCESS_KEY`: Volcengine speech access token used by `X-Api-Access-Key`
- `VOLCENGINE_ASR_RESOURCE_ID`: Volcengine speech resource ID, e.g. `volc.seedasr.sauc.duration`
- `VOLCENGINE_ASR_WS_URL`: Volcengine streaming ASR websocket endpoint
- `VOLCENGINE_ASR_NOSTREAM_WS_URL`: Volcengine nostream websocket endpoint used for upload transcription
- `VOLCENGINE_ASR_SSD_VERSION`: Volcengine SSD version required for native speaker clustering
- `DIARIZATION_MODE`: `disabled`, `offline`, or `hybrid`; `hybrid` only applies to DashScope `paraformer-realtime-v1`
- `DIARIZATION_MODEL`: final offline pyannote model, executed in the main backend venv
- `HUGGINGFACE_TOKEN`: Hugging Face token used to download pyannote and diart models
- `HF_HOME`: project-local Hugging Face cache directory; relative paths are resolved from the project root
- `PYANNOTE_CACHE`: pyannote.audio 3.x cache directory; set to the same Hugging Face hub cache used by diart
- `HF_HUB_DISABLE_SYMLINKS`: set to `1` on Windows to avoid Hugging Face cache symlink permission errors
- `HF_HUB_OFFLINE`: set to `1` after models are downloaded; keep `0` or remove it when changing models or downloading for the first time
- `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`: set to `1` so trusted pyannote.audio 3.x checkpoints load on PyTorch 2.6+
- `REALTIME_DIARIZATION_DURATION_SECONDS`: diart realtime processing window length for `hybrid`
- `REALTIME_DIARIZATION_STEP_SECONDS`: diart realtime window step for `hybrid`
- `REALTIME_DIARIZATION_LATENCY_SECONDS`: diart realtime latency target for `hybrid`
- `DIART_SEGMENTATION_MODEL`: diart segmentation model, for example `pyannote/segmentation`
- `DIART_EMBEDDING_MODEL`: diart embedding model, for example `pyannote/embedding`
- `DIART_PYTHON_PATH`: optional Python executable for a separate diart worker venv
- `FFMPEG_BINARY`: ffmpeg binary path for upload transcription endpoints
- `MEETING_HISTORY_DB_PATH`: SQLite file path for persisted meeting history

Speaker diarization behavior:

- Volcengine/Doubao uses native speaker clustering returned by the provider.
- DashScope `paraformer-realtime-v1` with `DIARIZATION_MODE=offline` assigns speakers after the meeting ends by running `DIARIZATION_MODEL`.
- DashScope `paraformer-realtime-v1` with `DIARIZATION_MODE=hybrid` emits live speaker updates through diart during the meeting, then confirms final speakers with pyannote after the meeting ends.

If diarization is disabled or unavailable, the backend still starts and serves requests. Speaker labels remain `Unknown` instead of failing the session.

By default, Hugging Face downloads are configured to use `models/huggingface` inside this project. The `models/` directory is local runtime data and is ignored by Git. On Windows, `HF_HUB_DISABLE_SYMLINKS=1` avoids `WinError 1314` when the terminal is not running with symlink privileges. `PYANNOTE_CACHE=models/huggingface/hub` lets pyannote.audio 3.x reuse the same project-local cache, and `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` keeps trusted pyannote checkpoints compatible with PyTorch 2.6+.

After all required models are pre-downloaded, set `HF_HUB_OFFLINE=1` locally to avoid Hugging Face HEAD retry logs and use the project cache directly. When changing models or downloading them for the first time, set it back to `0` or remove it.

### Optional diart worker environment

`diart==0.9.2` requires `numpy<2`, while the main backend pyannote stack uses `pyannote.audio` 4.x and `numpy>=2`. Keep realtime diart in a separate environment and point `DIART_PYTHON_PATH` at it:

```powershell
cd backend
.\.venv\Scripts\python.exe -m venv .venv-diart
.\.venv-diart\Scripts\python.exe -m pip install -i https://pypi.org/simple -r requirements-diart.txt
```

Example:

```env
DIART_PYTHON_PATH=D:\Project\smart-meeting-assistant\backend\.venv-diart\Scripts\python.exe
```

### Optional advanced variables

- `DASHSCOPE_ASR_WS_URL`
- `DASHSCOPE_WORKSPACE_ID`

### Frontend local overrides

If the frontend should connect to a non-default backend:

```bash
cp frontend/.env.example frontend/.env.local
```

Example:

```bash
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
```

## Local Development

### Start backend

Backend commands must use the existing virtual environment at `backend\.venv`. Do not use system Python, global pip, global pytest, or global uvicorn for backend work.

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Windows PowerShell:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Backend URL:

- `http://localhost:8080`

### Start frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- `http://localhost:5173`

## Electron Desktop Client

The first desktop client is a Windows-first Electron portable build. It wraps the existing React/Vite frontend only; it does not bundle or start the Python/FastAPI backend.

Start the backend before using the desktop client:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

To point the desktop client at a backend, configure `frontend/.env.local`:

```bash
VITE_WS_BASE_URL=ws://localhost:8080
```

Run Electron in development:

```powershell
cd frontend
npm install
npm run dev:electron
```

Build the Windows portable app:

```powershell
cd frontend
npm run electron:pack
```

The portable executable is generated under `frontend/release/`. The FastAPI backend must still be running at `localhost:8080` or the configured backend URL.

## Docker

```bash
docker-compose up --build
```

Docker URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8080`

The frontend container serves a built Vite app with `npm run preview`; it uses
the same browser-facing port as local development for consistency.
The backend stores meeting history in the `backend-data` Docker volume.

## API

### HTTP

- `GET /`
- `GET /api/health`
- `GET /api/meetings`
- `GET /api/meetings/{meeting_id}`
- `PATCH /api/meetings/{meeting_id}/title`
- `PATCH /api/meetings/{meeting_id}/summary`
- `PATCH /api/meetings/{meeting_id}/action-items/{action_item_index}`
- `DELETE /api/meetings/{meeting_id}`
- `POST /api/meetings/upload`
- `POST /api/transcribe`
- `POST /api/transcribe/batch`

### WebSocket

Connection examples:

```text
ws://localhost:8080/ws/meeting?scene=general&target_lang=en
ws://localhost:8080/ws/meeting?scene=finance&target_lang=zh
ws://localhost:8080/ws/meeting?scene=hr&target_lang=ja
ws://localhost:8080/ws/meeting?scene=general&target_lang=en&provider=volcengine
```

Supported websocket event types:

#### `session_started`

```json
{
  "type": "session_started",
  "data": {
    "meeting_id": "1c4f8c5ef3d74f6388d48da5ef4d23a0",
    "status": "draft",
    "created_at": "2026-04-25T15:01:02.345678Z",
    "scene": "general",
    "target_lang": "en",
    "provider": "volcengine",
    "source_type": "live"
  }
}
```

#### `transcript`

```json
{
  "type": "transcript",
  "data": {
    "transcript_index": 0,
    "speaker": "Unknown",
    "speaker_is_final": false,
    "transcript_is_final": false,
    "text": "Meeting content",
    "start": 0.0,
    "end": 1.5
  }
}
```

#### `transcript_update`

```json
{
  "type": "transcript_update",
  "data": {
    "transcript_index": 0,
    "speaker": "Speaker 1",
    "speaker_is_final": true,
    "transcript_is_final": true,
    "text": "Meeting content",
    "start": 0.0,
    "end": 1.5
  }
}
```

#### `speaker_update`

```json
{
  "type": "speaker_update",
  "data": {
    "transcript_index": 0,
    "speaker": "Speaker 1",
    "speaker_is_final": true
  }
}
```

#### `translation`

```json
{
  "type": "translation",
  "data": {
    "transcript_index": 0,
    "target_lang": "en",
    "text": "Hello everyone."
  }
}
```

#### `analysis`

```json
{
  "type": "analysis",
  "data": {
    "overall_sentiment": "mixed",
    "engagement_level": "medium",
    "engagement_summary": "The discussion shows clear disagreement with active participation.",
    "signal_counts": {
      "agreement": 2,
      "disagreement": 1,
      "tension": 1,
      "hesitation": 1
    },
    "highlights": [
      {
        "transcript_index": 4,
        "signal": "disagreement",
        "severity": "medium",
        "reason": "The speaker clearly opposes the proposal."
      }
    ]
  }
}
```

#### `summary`

```json
{
  "type": "summary",
  "data": {
    "title": "Weekly Report Delivery",
    "overview": "The team reviewed the weekly report and aligned on the delivery plan. They confirmed the final owner and timeline for the update.",
    "key_topics": [
      "Weekly report",
      "Delivery plan"
    ],
    "decisions": [
      "Finalize the weekly report on Friday"
    ],
    "action_items": [
      {
        "task": "Send the report by Friday",
        "assignee": "Speaker 1",
        "deadline": "Friday",
        "status": "pending",
        "source_excerpt": "I will send the report by Friday.",
        "transcript_index": 3,
        "is_actionable": true,
        "confidence": 0.93,
        "owner_explicit": true,
        "deadline_explicit": true
      }
    ],
    "risks": []
  }
}
```

#### `error`

```json
{
  "type": "error",
  "data": "error message"
}
```

#### Finalize message sent by the frontend

```json
{
  "type": "finalize"
}
```

### Meeting history responses

#### `POST /api/meetings/upload`

```json
{
  "meeting_id": "f4a6d58cb28b4d2a8d8f8d0cb014b10a",
  "status": "processing",
  "source_type": "upload",
  "scene": "general",
  "target_lang": "en",
  "provider": "dashscope",
  "created_at": "2026-04-26T02:10:00.000000Z",
  "updated_at": "2026-04-26T02:10:00.000000Z",
  "title": "",
  "title_manually_edited": false,
  "summary_manually_edited": false,
  "transcript_count": 0,
  "preview_text": "",
  "processing_stage": "transcribing",
  "error_message": null,
  "source_name": "meeting.wav",
  "transcripts": [],
  "summary": null,
  "analysis": null
}
```

#### `GET /api/meetings`

```json
[
  {
    "meeting_id": "1c4f8c5ef3d74f6388d48da5ef4d23a0",
    "status": "finalized",
    "source_type": "live",
    "scene": "general",
    "target_lang": "en",
    "provider": "volcengine",
    "created_at": "2026-04-25T15:01:02.345678Z",
    "updated_at": "2026-04-25T15:08:20.123456Z",
    "title": "Launch Plan Review",
    "title_manually_edited": false,
    "summary_manually_edited": false,
    "transcript_count": 18,
    "preview_text": "The team aligned on the launch plan and concrete follow-up actions.",
    "processing_stage": null,
    "error_message": null,
    "source_name": null
  }
]
```

#### `GET /api/meetings/{meeting_id}`

```json
{
  "meeting_id": "1c4f8c5ef3d74f6388d48da5ef4d23a0",
  "status": "finalized",
  "source_type": "upload",
  "scene": "general",
  "target_lang": "en",
  "provider": "volcengine",
  "created_at": "2026-04-25T15:01:02.345678Z",
  "updated_at": "2026-04-25T15:08:20.123456Z",
  "title": "Launch Plan Review",
  "title_manually_edited": false,
  "summary_manually_edited": false,
  "transcript_count": 18,
  "preview_text": "The team aligned on the launch plan and concrete follow-up actions.",
  "processing_stage": null,
  "error_message": null,
  "source_name": "meeting.wav",
  "transcripts": [
    {
      "transcript_index": 0,
      "speaker": "Speaker 1",
      "speaker_is_final": true,
      "transcript_is_final": true,
      "text": "Let's finalize the launch plan.",
      "start": 0.0,
      "end": 1.4,
      "translated_text": "让我们敲定发布计划。",
      "translated_target_lang": "zh"
    }
  ],
  "summary": {
    "title": "Launch Plan Review",
    "overview": "The team aligned on the launch plan and concrete follow-up actions.",
    "key_topics": [
      "Launch plan"
    ],
    "action_items": [],
    "decisions": [],
    "risks": []
  },
  "analysis": {
    "overall_sentiment": "neutral",
    "engagement_level": "medium",
    "engagement_summary": "The meeting remained focused with steady participation.",
    "signal_counts": {
      "agreement": 1,
      "disagreement": 0,
      "tension": 0,
      "hesitation": 0
    },
    "highlights": []
  }
}
```

#### `PATCH /api/meetings/{meeting_id}/title`

```json
{
  "title": "Customer Launch Planning"
}
```

#### `PATCH /api/meetings/{meeting_id}/summary`

```json
{
  "overview": "The team aligned on launch scope, owners, and next steps.",
  "key_topics": ["Launch scope", "Owner assignment"],
  "decisions": ["Proceed with the launch plan"],
  "risks": ["Timeline depends on final budget approval"],
  "action_items": [
    {
      "task": "Send the launch checklist",
      "assignee": "Speaker 1",
      "deadline": "Friday",
      "status": "pending",
      "source_excerpt": "I will send the checklist by Friday.",
      "transcript_index": 3,
      "is_actionable": true,
      "confidence": 0.93,
      "owner_explicit": true,
      "deadline_explicit": true
    }
  ]
}
```

#### `PATCH /api/meetings/{meeting_id}/action-items/{action_item_index}`

```json
{
  "status": "completed"
}
```

## Meeting Scenes

### `general` (Default)

- General meeting discussions
- Action items
- Decisions
- Risks

### `finance`

- Finance / business review discussions
- Action items
- Decisions
- Risks

### `hr`

- Interview / hiring conversations
- Follow-up actions
- Interview conclusions
- Risks

## Manual Test Scripts

- `FULL_FEATURE_TEST_SCRIPT.md`: end-to-end test script for transcript, translation, summary, and analysis

## Current Limitations

- Hybrid realtime speaker diarization labels are provisional and can jump or split one speaker into multiple temporary labels; final pyannote labels after `finalize` remain authoritative
- Volcengine native speaker clustering currently applies only to the ASR provider path; translation / summary / analysis still run on DashScope
- Summary is now generated only after `finalize`; it is no longer refreshed during the meeting
- Realtime ASR can still misrecognize technical terms and English words
- Summary combines model output with lightweight rule augmentation
- Meeting analysis combines model output with lightweight rule fallback for obvious Chinese emotional signals
- Sentiment / engagement analysis is meeting-level, not participant-level
- Mobile browser recording compatibility is less reliable than desktop
- Meeting history currently stores metadata, transcripts, translations, summary, and analysis, but not raw audio files
- Upload processing is currently async but still in-process; there is no distributed worker queue yet
- `POST /api/transcribe` and `POST /api/transcribe/batch` remain transcript-only utility/debug endpoints

## License

MIT
