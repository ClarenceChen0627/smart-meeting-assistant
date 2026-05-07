# Smart Meeting Assistant

Language:
- English: `README.md`
- 简体中文: [README-zh.md](README-zh.md)

Smart Meeting Assistant is a React 18 + FastAPI meeting copilot for live transcription, transcript translation, meeting summaries, action items, sentiment / engagement analysis, upload processing, and saved meeting history. The frontend runs in a browser or in a Windows-first Electron desktop shell.

## Quick Start

### 1. Run without external AI keys

Demo mode is the fastest way to verify the full product workflow locally. It uses deterministic mock ASR, translation, summary, and analysis.

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

Edit `.env`:

```env
DEMO_MODE=1
DEFAULT_ASR_PROVIDER=demo
DIARIZATION_MODE=disabled
```

Start the backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open:

- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:8080/api/health`

### 2. Run with real providers

Copy `.env.example` to `.env`, add provider credentials, and choose:

- `DEFAULT_ASR_PROVIDER=volcengine` for Volcengine Doubao ASR.
- `DEFAULT_ASR_PROVIDER=dashscope` for DashScope Paraformer realtime ASR.

Use [Configuration](docs/configuration.md) for the minimal variable matrix and diarization prerequisites.

## Features

- Live microphone capture over WebSocket.
- Switchable ASR providers: Volcengine Doubao, DashScope Paraformer, and local demo.
- Realtime transcript rendering with speaker labels.
- Transcript translation to 10 target languages.
- Final meeting summary with title, overview, key topics, decisions, risks, and action items.
- Incremental and final sentiment / engagement analysis.
- Upload meeting mode with async processing and progressive polling.
- SQLite-backed meeting history for live and uploaded meetings.
- Editable saved titles, summary fields, and action item status.
- Optional Windows portable Electron client.

## Project Structure

```text
smart-meeting-assistant/
├─ frontend/              React + Vite UI and Electron shell
├─ backend/               FastAPI backend
├─ backend/tests/         pytest backend tests
├─ data/                  local runtime data
├─ docs/                  architecture, API, and configuration docs
├─ .env.example           backend environment template
├─ docker-compose.yml
├─ README.md
└─ README-zh.md
```

## Common Commands

Backend commands must use the repository virtual environment:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run test
npm run build
npm run dev
```

```bash
cd frontend
npm install
npm run test
npm run build
npm run dev
```

Electron:

```powershell
cd frontend
npm run dev:electron
npm run electron:pack
```

```bash
cd frontend
npm run dev:electron
npm run electron:pack
```

Docker:

```powershell
docker-compose up --build
```

```bash
docker-compose up --build
```

## Documentation

- [Architecture](docs/architecture.md): system overview, realtime flow, upload flow, and meeting state diagrams.
- [Configuration](docs/configuration.md): demo mode, provider variables, frontend overrides, and minimum setup matrix.
- [API Reference](docs/api.md): HTTP endpoints, WebSocket messages, and meeting record fields.
- [Speaker Diarization](docs/diarization.md): offline and hybrid diarization setup.
- [diart Setup](docs/diart.md): detailed Windows setup notes for realtime diart speaker updates ([中文](docs/zh/diart.md)).
- [Requirements](docs/requirements/project-requirements.md): original project requirements and implementation comparison ([comparison](docs/requirements/requirements-comparison.md), [中文](docs/zh/requirements/project-requirements.md), [中文对比](docs/zh/requirements/requirements-comparison.md)).
- [Technical Implementation](docs/technical-implementation.md): English implementation notes.
- [中文技术实现](docs/zh/technical-implementation.md): Chinese implementation notes.

## Current Limitations

- Hybrid realtime diarization labels are provisional until final pyannote confirmation.
- Volcengine native speaker clustering applies only to the Volcengine ASR provider path.
- Summary is generated after `finalize`, not continuously refreshed during the meeting.
- Realtime ASR can misrecognize technical terms.
- Meeting analysis is meeting-level, not participant-level.
- Mobile browser recording is less reliable than desktop.
- Meeting history stores metadata, transcripts, translations, summaries, and analysis, but not raw audio files.
- Upload processing is async but still in-process; there is no distributed worker queue yet.

## Roadmap

- Short term: keep demo mode stable, broaden smoke tests, and add screenshots or clips for visible UI changes.
- Medium term: add frontend interaction tests, export meeting notes, and improve upload retry/error recovery.
- Long term: introduce background workers, optional raw audio retention, participant-level analysis, and custom terminology support.

## License

MIT
