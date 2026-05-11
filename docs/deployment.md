# Deployment

Language:
- English: `deployment.md`

Smart Meeting Assistant is designed for private self-hosting. Production deployments should run the FastAPI backend behind HTTPS and expose the React frontend from the same HTTPS origin or from an explicitly allowed origin.

## Recommended Production Shape

- Backend: FastAPI on `127.0.0.1:8080` or an internal Docker network.
- Frontend: static Vite build served by a web server or the provided frontend container.
- Reverse proxy: terminates HTTPS and forwards HTTP API traffic plus `/ws/meeting` WebSocket upgrades to the backend.
- Storage: persistent volume for `MEETING_HISTORY_DB_PATH`, `UPLOAD_QUEUE_DIR`, and optional `RAW_AUDIO_DIR`.

## Required Security Settings

Set these before exposing the app outside a trusted development machine:

```env
API_ACCESS_TOKEN=replace-with-a-long-random-token
CORS_ALLOW_ORIGINS=https://meetings.example.com
MAX_UPLOAD_BYTES=524288000
ALLOWED_UPLOAD_CONTENT_TYPES=audio/wav,audio/x-wav,audio/mpeg,audio/mp3,audio/mp4,audio/webm,audio/ogg,video/webm,application/octet-stream
```

`/` and `/api/health` stay public for basic uptime checks. Meeting data, uploads, diagnostics, audit events, glossary APIs, transcript utilities, and `/ws/meeting` require the token when `API_ACCESS_TOKEN` is set.

The browser stores the access token in local storage after the user enters it in the UI. WebSocket authentication uses an `access_token` query parameter because browser WebSocket APIs do not support arbitrary request headers. Configure proxy access logs so query strings are not retained if this is a concern.

## Reverse Proxy Notes

The proxy must forward:

- `/api/*` to the backend HTTP service.
- `/ws/meeting` to the backend with WebSocket upgrade headers.
- Static frontend assets to the frontend server or static file root.

Mobile microphone capture requires HTTPS or another secure context. For LAN phone testing, use HTTPS on the LAN hostname instead of plain HTTP.

## Config Check

Run the read-only configuration check before first use:

```powershell
cd backend
.\.venv\Scripts\python.exe tools\check_config.py
```

```bash
cd backend
./.venv/Scripts/python.exe tools/check_config.py
```

The check reports missing provider keys and paths without printing secret values.
