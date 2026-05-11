# Smoke Testing

Use demo mode for fast local verification without external AI provider keys.

## Backend

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```env
DEMO_MODE=1
DEFAULT_ASR_PROVIDER=demo
DIARIZATION_MODE=disabled
```

Run checks:

```powershell
cd backend
.\.venv\Scripts\python.exe tools\check_config.py
.\.venv\Scripts\python.exe -m pytest -m smoke
```

## Frontend

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
```

## Manual Flow

1. Start backend and frontend only when manual verification is needed.
2. Open the frontend and confirm `/api/health` is reachable.
3. Start a demo live meeting, stop it, and confirm transcript, summary, action items, and history save.
4. Upload a small audio file in demo mode and confirm polling reaches `finalized`.
5. Open Meeting History, search/filter records, toggle favorite/archive, and edit tags.
6. Export standard notes, Chinese minutes, and action items Markdown.
7. Set `API_ACCESS_TOKEN`, restart the backend, confirm unauthenticated protected requests fail, enter the token in the UI, and confirm the same flow works.
