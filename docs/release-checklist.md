# Release Checklist

Use this checklist before tagging or sharing a self-hosted release.

## Configuration

- `.env.example` includes every required backend variable.
- `frontend/.env.example` includes only public frontend URL overrides.
- `API_ACCESS_TOKEN` and `CORS_ALLOW_ORIGINS` are documented for production.
- `backend/tools/check_config.py` runs without unexpected `ERROR` entries.

## Verification

- Backend tests pass:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

- Frontend tests and build pass:

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
```

- Demo mode smoke flow covers live meeting, upload meeting, saved history detail, and Markdown export.

## Documentation

- `README.md` points to configuration, deployment, API, and smoke testing docs.
- Known limits are current: token auth is basic self-hosted protection, no account system exists, and Word/PDF export is not part of this release.
- Screenshots are refreshed only when the visible workflow changed.
