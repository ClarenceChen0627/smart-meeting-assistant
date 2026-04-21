# Smart Meeting Assistant

Language:
- English: `README.md`
- 简体中文: [README-zh.md](README-zh.md)

Smart Meeting Assistant is a browser-based meeting copilot built with React 18 and FastAPI. It supports live speech transcription, live transcript translation, meeting summarization, action-item extraction, and meeting sentiment / engagement analysis over a WebSocket-based realtime workflow.

## Architecture

- `frontend`: React 18 + TypeScript + Vite + Tailwind CSS
- `backend`: FastAPI + Uvicorn

## Features

### Realtime pipeline

- Browser microphone capture
- Realtime ASR with DashScope Paraformer (`paraformer-realtime-v1`)
- Realtime transcript rendering
- Realtime transcript translation to one target language:
  - English
  - Japanese
  - Korean

### Meeting summary

- Final summary after recording stops
- Structured output:
  - `todos`
  - `decisions`
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

### Upload transcription

- `POST /api/transcribe`
- `POST /api/transcribe/batch`

Uploaded audio is normalized with `ffmpeg` before being transcribed.

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
8. The backend finishes ASR, sends the final `analysis`, sends the final `summary`, then closes the socket.

## Requirements

- Node.js 18+
- Python 3.10+
- ffmpeg
- A valid DashScope API key

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

PORT=8080
LOG_LEVEL=INFO
SUMMARY_INTERVAL=10
FFMPEG_BINARY=ffmpeg
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
```

### Important variables

- `DASHSCOPE_API_KEY`: used by ASR, translation, summary, and meeting analysis
- `DASHSCOPE_MODEL`: used by summary and meeting analysis
- `DASHSCOPE_ASR_MODEL`: realtime ASR model
- `DASHSCOPE_TRANSLATION_MODEL`: transcript translation model
- `SUMMARY_INTERVAL`: transcript count threshold for interim summary generation
- `FFMPEG_BINARY`: ffmpeg binary path for upload transcription endpoints

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
ws://localhost:8080/ws/meeting?scene=finance&target_lang=en
ws://localhost:8080/ws/meeting?scene=hr&target_lang=ja
```

Supported websocket event types:

#### `transcript`

```json
{
  "type": "transcript",
  "data": {
    "speaker": "Speaker_A",
    "text": "Meeting content",
    "start": 0.0,
    "end": 1.5
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
    "todos": [],
    "decisions": [],
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

- `speaker` assignment is still placeholder logic, not true diarization
- Realtime ASR can still misrecognize technical terms and English words
- Summary combines model output with lightweight rule augmentation
- Meeting analysis combines model output with lightweight rule fallback for obvious Chinese emotional signals
- Sentiment / engagement analysis is meeting-level, not participant-level
- Mobile browser recording compatibility is less reliable than desktop

## License

MIT
