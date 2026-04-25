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
- Realtime transcript rendering with provisional `Unknown` speaker labels
- Offline speaker diarization on `finalize`, with speaker updates streamed back to the frontend
- Real-time transcript translation to a target language, currently supporting 10 languages including:
  - English, Spanish, French, German, Chinese
  - Japanese, Korean, Portuguese, Arabic, Hindi

### Meeting summary

- Final summary after recording stops
- Structured output:
  - `overview`
  - `key_topics`
  - `decisions`
  - `action_items`
  - `risks`

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

- Resizable sidebar and transcript workspace on desktop
- Scrollable transcript list
- Bilingual transcript cards
- Separate Meeting Summary and Meeting Analysis panels
- Optional Windows portable Electron desktop client

### Upload transcription

- `POST /api/transcribe`
- `POST /api/transcribe/batch`

Uploaded audio is normalized with `ffmpeg` before being transcribed.
When offline diarization is enabled, uploaded files also return final speaker labels.

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
3. The backend forwards audio to DashScope realtime ASR.
4. The backend emits `transcript` messages.
5. The backend translates transcript text and emits `translation` messages.
6. The backend periodically analyzes emotional dynamics and emits `analysis` messages.
7. When recording stops, the frontend sends `finalize`.
8. The backend closes the session WAV, runs offline speaker diarization, emits `speaker_update` messages, sends the final `analysis`, sends the final `summary`, then closes the socket.

## Requirements

- Node.js 18+
- Python 3.10+
- ffmpeg
- A valid DashScope API key
- Optional: a Hugging Face access token for offline speaker diarization

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
DIARIZATION_MODEL=pyannote/speaker-diarization-community-1
HUGGINGFACE_TOKEN=

PORT=8080
LOG_LEVEL=INFO
FFMPEG_BINARY=ffmpeg
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
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
- `DIARIZATION_MODE`: set to `offline` to enable finalize-time speaker diarization
- `DIARIZATION_MODEL`: offline diarization model name
- `HUGGINGFACE_TOKEN`: Hugging Face token used to download the diarization model
- `FFMPEG_BINARY`: ffmpeg binary path for upload transcription endpoints

If diarization is disabled or unavailable, the backend still starts and serves requests. Speaker labels remain `Unknown` instead of failing the session.

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

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
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
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
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

## API

### HTTP

- `GET /`
- `GET /api/health`
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

- Speaker diarization is currently offline-only and runs after `finalize`, not during live capture
- Volcengine native speaker clustering currently applies only to the ASR provider path; translation / summary / analysis still run on DashScope
- Summary is now generated only after `finalize`; it is no longer refreshed during the meeting
- Realtime ASR can still misrecognize technical terms and English words
- Summary combines model output with lightweight rule augmentation
- Meeting analysis combines model output with lightweight rule fallback for obvious Chinese emotional signals
- Sentiment / engagement analysis is meeting-level, not participant-level
- Mobile browser recording compatibility is less reliable than desktop

## License

MIT
