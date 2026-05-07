# Smart Meeting Assistant Technical Implementation

Language:
- English: `technical-implementation.md`
- 简体中文: [zh/technical-implementation.md](zh/technical-implementation.md)

This document explains how the current repository implements the five baseline requirements from [`docs/requirements/project-requirements.md`](requirements/project-requirements.md), plus the product and engineering capabilities that have been added around them.

## 1. System Architecture

The project uses a React/Electron frontend, a FastAPI backend, third-party or demo AI providers, and SQLite persistence.

```text
smart-meeting-assistant/
├─ backend/
│  └─ app/
│     ├─ main.py                         # FastAPI startup and service wiring
│     ├─ api/                            # HTTP and WebSocket APIs
│     ├─ clients/                        # ASR and LLM provider clients
│     ├─ services/                       # Business workflow services
│     └─ schemas/                        # Pydantic models
├─ frontend/
│  ├─ src/
│  │  ├─ app/App.tsx                     # Main frontend state orchestration
│  │  ├─ app/components/                 # Transcript, summary, actions, analysis panels
│  │  ├─ hooks/useAudioRecording.ts      # Browser microphone capture and PCM encoding
│  │  ├─ hooks/useWebSocket.ts           # Live meeting WebSocket client
│  │  └─ types/index.ts                  # Shared TypeScript data shapes
│  └─ electron/main.cjs                  # Electron desktop shell
└─ data/meeting_history.sqlite3          # Local SQLite meeting history
```

`backend/app/main.py` is the backend composition root. During FastAPI lifespan startup, it creates provider clients, workflow services, SQLite history storage, upload processing, and the live `SessionManager`, then exposes them through `app.state`.

## 2. Requirement-To-Implementation Map

| Requirement | Main implementation | Behavior |
| --- | --- | --- |
| Realtime speech-to-text with speakers | `useAudioRecording.ts`, `useWebSocket.ts`, `/ws/meeting`, `SessionManager`, `ASRProviderService`, ASR clients, diarization services | Frontend streams 16 kHz PCM audio to FastAPI; backend forwards audio to the selected ASR provider; speaker labels come from Volcengine, demo data, or DashScope plus diarization. |
| Meeting summarization | `SummaryService`, `MeetingSummary`, `SummaryPanel.tsx` | Final transcript rows are sent to the configured LLM or demo client; JSON is parsed, cleaned, augmented, persisted, and rendered. |
| Transcript translation | `TranslationService`, `DashScopeClient.translate_text`, `SessionManager._consume_translations`, `TranscriptPanel.tsx` | Final transcript rows are translated to one selected target language and saved with the transcript row. |
| Context-aware action items | `SummaryService`, `ActionItem`, `ActionItemsPanel.tsx`, meeting history APIs | The model returns action items; backend rules filter and augment them; the frontend supports editing and completion status updates. |
| Sentiment and engagement analysis | `SentimentAnalysisService`, `MeetingAnalysis`, `MeetingAnalysisPanel.tsx` | The backend creates incremental and final meeting-level analysis snapshots, with rule fallback for obvious interaction signals. |

## 3. Live Meeting Workflow

The live workflow starts in `frontend/src/app/App.tsx`:

1. The frontend builds a WebSocket URL with `scene`, `target_lang`, and `provider`.
2. `useWebSocket.connect()` opens `/ws/meeting`.
3. `useAudioRecording.startRecording()` gets microphone access and starts browser audio processing.
4. Audio is downsampled to 16 kHz PCM and sent as binary WebSocket frames.
5. `backend/app/api/websocket.py` accepts the socket and delegates to `SessionManager`.
6. `SessionManager.create_session()` creates a draft meeting in SQLite, starts ASR consumption, and emits `session_started`.
7. ASR segments are normalized into `TranscriptItem` rows, persisted, and emitted as `transcript` or `transcript_update`.
8. Final transcript rows can trigger translation and periodic analysis.
9. On `{ "type": "finalize" }`, the backend finishes ASR, runs final speaker confirmation when enabled, emits final analysis and summary, marks the meeting finalized, and closes the socket.

## 4. ASR Provider Selection

`ASRProviderService` resolves the active ASR provider. Supported providers are:

- `volcengine`: default production ASR path with native speaker clustering.
- `dashscope`: DashScope Paraformer realtime ASR, optionally combined with offline or hybrid diarization.
- `demo`: deterministic local ASR used when `DEMO_MODE=1`.

The demo provider follows the same `ASRClient` / `ASRStream` protocol as real providers. This lets WebSocket sessions, uploads, summaries, translations, analysis, and history records run without external API keys.

When `provider=demo` is requested while `DEMO_MODE=0`, the backend stays on the demo provider and reports that it is not configured instead of silently pretending to use a real provider.

## 5. Speaker Diarization

Speaker handling has three paths:

- Volcengine can return provider-native speaker labels.
- DashScope with `DIARIZATION_MODE=offline` assigns speakers after the meeting ends by running pyannote.
- DashScope with `DIARIZATION_MODE=hybrid` can emit provisional live speaker updates through diart, then confirm final labels with pyannote after finalize.

The high-level setup is documented in [`diarization.md`](diarization.md). Detailed Windows diart setup is documented in [`diart.md`](diart.md).

## 6. Upload Meeting Workflow

The product upload path is `POST /api/meetings/upload`.

1. The frontend submits one audio file plus `scene`, `target_lang`, and `provider`.
2. The backend creates a `processing` meeting record with `source_type=upload`.
3. `UploadMeetingService` processes the file in a background task.
4. Non-demo uploads are converted to WAV with ffmpeg.
5. Demo uploads skip ffmpeg conversion and use deterministic transcript rows.
6. ASR transcript rows are persisted first so the frontend can show partial progress.
7. Translation, analysis, and summary are generated and persisted.
8. The meeting is marked `finalized` on success or `failed` on unrecoverable errors.

The frontend polls `GET /api/meetings/{meeting_id}` and renders transcript, analysis, summary, and action items in the same workspace used by live meetings.

## 7. Meeting History

`MeetingHistoryService` stores local meeting history in SQLite. It persists:

- meeting metadata and status
- live/upload source type
- provider, scene, and target language
- transcript rows
- transcript translations
- meeting summary
- meeting analysis
- generated or manually edited titles
- manually edited summary fields
- action item status/content updates

The history APIs support list, detail, title update, summary update, action item status update, and deletion.

## 8. Frontend State Model

`App.tsx` owns the main product state:

- current input mode: `live` or `upload`
- selected ASR provider, scene, and translation target
- live recording and finalization state
- active upload meeting state
- selected history meeting state
- transcript, summary, action item, and analysis display state

The top-level Live / Upload switch reuses the same result workspace. Historical meetings override the current live/upload view until the user exits history selection.

## 9. Configuration And Demo Mode

Configuration is environment-variable driven. Important variables include:

- `DEMO_MODE`: enables deterministic local demo providers.
- `DEFAULT_ASR_PROVIDER`: `volcengine`, `dashscope`, or `demo`.
- `DASHSCOPE_API_KEY`: used by DashScope ASR, translation, summary, and analysis.
- `VOLCENGINE_ASR_APP_KEY` and `VOLCENGINE_ASR_ACCESS_KEY`: used by Volcengine ASR.
- `DIARIZATION_MODE`: `disabled`, `offline`, or `hybrid`.
- `MEETING_HISTORY_DB_PATH`: SQLite meeting history location.

`GET /api/health` reports `demoMode`, configured provider status, and available ASR providers.

## 10. Tests And CI

Backend tests use pytest and must run through `backend/.venv`. Existing coverage includes:

- summary parsing and action item extraction behavior
- diarization assignment behavior
- live WebSocket workflow
- upload workflow
- history persistence and migration
- demo provider health, WebSocket, upload, and disabled-mode behavior

The frontend currently has a lightweight Node-based test for upload status messaging and continues to rely on `npm run build` as the primary UI verification step.

The Windows-first CI workflow installs backend and frontend dependencies, runs backend pytest, runs frontend tests, and builds the Vite frontend.

## 11. Demo Screenshot Refresh

Demo UI screenshots live in `docs/assets/screenshots/` and are linked from both README files. Refresh them only from demo mode so the images do not require external provider keys.

Recommended flow:

1. Start the backend with `DEMO_MODE=1`, `DEFAULT_ASR_PROVIDER=demo`, `DIARIZATION_MODE=disabled`, and a temporary local `MEETING_HISTORY_DB_PATH`.
2. Build the frontend with `cd frontend` and `npm.cmd run build` on Windows PowerShell.
3. Use the existing Electron dependency to load `frontend/dist/index.html` and capture the live demo workspace, upload completion state, and saved meeting detail.
4. Wait for UI state changes to render before capture. In automation, wait for the expected text and then wait at least two `requestAnimationFrame` ticks before calling Electron `capturePage()`.
5. Commit only the final PNG files under `docs/assets/screenshots/`. Do not commit temporary capture scripts, local SQLite files, large recordings, or dependency upgrades for screenshot capture.

If PowerShell blocks `npm.ps1`, use `npm.cmd`. Electron does not need to be upgraded for screenshot refreshes; use the dependency already present in `frontend/node_modules`.

## 12. Current Boundaries

- Summary generation happens after finalize or upload completion, not continuously during a live meeting.
- Translation supports one target language per meeting.
- Raw audio is not stored in meeting history.
- Upload processing is async but still in-process; there is no distributed worker queue.
- Sentiment and engagement analysis is meeting-level, not participant-level.
- Demo mode is for onboarding, local smoke tests, and CI. It does not represent real provider quality.
