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
| Sentiment and engagement analysis | `MeetingAnalysisService`, `MeetingAnalysis`, `MeetingAnalysisPanel.tsx` | The backend creates incremental and final meeting-level snapshots plus participant rollups for speaker engagement, speaking time, and interaction signals, with rule fallback for obvious cues. |
| Persistent terminology glossary | `GlossaryStoreService`, `GlossaryService`, `/api/glossary/terms`, `MeetingProcessingSettings.tsx` | Saved glossary terms are stored in SQLite and automatically merged into live and upload meetings before per-meeting correction, summary, and analysis prompts run. |

## 3. Live Meeting Workflow

The live workflow starts in `frontend/src/app/App.tsx`:

1. The frontend builds a WebSocket URL with `scene`, `target_lang`, and `provider`.
2. `useWebSocket.connect()` opens `/ws/meeting`.
3. `useAudioRecording.startRecording()` checks browser microphone and audio-processing support, gets microphone access, and starts browser audio processing.
4. The hook tracks microphone `ended` / `mute` / `unmute`, `AudioContext` state changes, page visibility, `pagehide`, and screen Wake Lock availability so mobile interruptions are surfaced to the user.
5. Audio is downsampled to 16 kHz PCM and sent as binary WebSocket frames.
6. `backend/app/api/websocket.py` accepts the socket and delegates to `SessionManager`.
7. `SessionManager.create_session()` creates a draft meeting in SQLite, starts ASR consumption, and emits `session_started`.
8. ASR segments are normalized into `TranscriptItem` rows, persisted, and emitted as `transcript` or `transcript_update`.
9. Final transcript rows can trigger translation, periodic analysis, and live rolling summaries.
10. On `{ "type": "finalize" }`, the backend finishes ASR, runs final speaker confirmation when enabled, emits final analysis and summary, marks the meeting finalized, and closes the socket.

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
3. `UploadMeetingService` writes the upload payload to `UPLOAD_QUEUE_DIR` and records a SQLite `upload_jobs` row.
4. The embedded upload worker claims queued jobs by default; `tools/run_upload_worker.py` can run the same worker out of process.
5. Non-demo uploads are converted to WAV with ffmpeg.
6. Demo uploads skip ffmpeg conversion and use deterministic transcript rows.
7. ASR transcript rows are persisted first so the frontend can show partial progress.
8. Translation, analysis, and summary are generated and persisted.
9. The meeting is marked `finalized` on success or `failed` on unrecoverable errors, and the temporary queue payload is removed.

The frontend polls `GET /api/meetings/{meeting_id}` and renders transcript, analysis, summary, and action items in the same workspace used by live meetings. Runtime ASR, analysis, and summary failures are retried once inside a single job attempt. If the full upload job still fails, the queue keeps the payload, records `last_error`, and retries with bounded exponential backoff until `UPLOAD_QUEUE_MAX_ATTEMPTS` is exhausted. Only terminal failures mark the meeting `failed`; retryable failures keep the meeting `processing`.

On startup, stale `processing` queue claims older than `UPLOAD_QUEUE_PROCESSING_TIMEOUT_SECONDS` are released back to `queued`. Processing upload meetings with no active queue job are marked interrupted. Missing queue payload files are unrecoverable and mark both the job and meeting failed. Queue payload files are temporary processing inputs and are separate from user-requested raw audio retention.

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
- manually edited speaker labels
- manually edited summary fields
- action item status/content updates

The history APIs support list, detail, title update, speaker rename/merge, summary update, action item status update, and deletion.

Speaker corrections are persisted through `PATCH /api/meetings/{meeting_id}/speakers` after a meeting reaches `finalized` or `failed`. The backend updates transcript rows, exact action item assignee references, and participant-level analysis rollups without rerunning LLM summary or analysis generation.

`GlossaryStoreService` uses the same local SQLite file to store global terminology terms. `GlossaryService.resolve_terms()` merges per-meeting terms, saved global terms, and `CUSTOM_GLOSSARY_TERMS` in that order, deduplicating by case-insensitive `term` and keeping the same 50-term processing limit.

`AuditLogService` also uses the same SQLite file and creates an `audit_events` table for successful manual edits and deletions. Each event stores `scope`, `meeting_id`, `entity_type`, `entity_id`, `action`, `field_path`, JSON `before` / `after` snapshots, JSON `metadata`, and `created_at`. Meeting-scoped events cover title, favorite/archive/tag metadata, summary, action item status, speaker correction edits, and compact meeting deletion metadata. Global events cover glossary term create/update/delete operations. The audit log intentionally does not record ASR/LLM generated content or upload worker state changes in v1.

Audit query APIs are read-only:

- `GET /api/meetings/{meeting_id}/audit-events` returns recent events for a saved meeting, newest first.
- `GET /api/audit-events?scope=global&entity_type=glossary_term` returns filtered audit events for local troubleshooting and future UI use. The same endpoint accepts `meeting_id` to retrieve compact deletion records after the meeting row has been removed.

Meeting notes can be exported from the summary panel as a Markdown file. The export is generated in the frontend from the displayed summary, meeting date, duration, risks, decisions, action items, and transcript references; no backend export endpoint is required.

## 8. Frontend State Model

`App.tsx` owns the main product state:

- current input mode: `live` or `upload`
- selected ASR provider, scene, and translation target
- live recording and finalization state
- active upload meeting state
- selected history meeting state
- transcript, summary, action item, and analysis display state
- selected meeting audit events
- saved glossary terms and per-meeting temporary glossary input

The top-level Live / Upload switch reuses the same result workspace. Historical meetings override the current live/upload view until the user exits history selection.

When a historical meeting is selected, the frontend loads meeting audit events into the history workspace and shows an `Audit` tab. Successful title, summary, action item, and speaker edits refresh the audit list after the meeting record update. Global glossary audit events are available through the API but are not shown in the meeting workspace.

## 9. Configuration And Demo Mode

Configuration is environment-variable driven. Important variables include:

- `DEMO_MODE`: enables deterministic local demo providers.
- `DEFAULT_ASR_PROVIDER`: `volcengine`, `dashscope`, or `demo`.
- `DASHSCOPE_API_KEY`: used by DashScope ASR, translation, summary, and analysis.
- `VOLCENGINE_ASR_APP_KEY` and `VOLCENGINE_ASR_ACCESS_KEY`: used by Volcengine ASR.
- `DIARIZATION_MODE`: `disabled`, `offline`, or `hybrid`.
- `MEETING_HISTORY_DB_PATH`: SQLite meeting history location.
- `UPLOAD_QUEUE_DIR`: temporary upload queue payload directory.
- `UPLOAD_QUEUE_EMBEDDED_WORKER_ENABLED`: controls whether FastAPI starts the embedded upload worker.
- `UPLOAD_QUEUE_MAX_ATTEMPTS`: maximum queue-level attempts per upload job.
- `UPLOAD_QUEUE_RETRY_BASE_SECONDS` and `UPLOAD_QUEUE_RETRY_MAX_SECONDS`: exponential backoff bounds for retryable upload job failures.
- `UPLOAD_QUEUE_PROCESSING_TIMEOUT_SECONDS`: stale processing claim timeout used during startup recovery.

`GET /api/health` reports `demoMode`, configured provider status, and available ASR providers.

## 10. Observability

HTTP requests pass through a lightweight observability middleware. The backend accepts or generates `X-Request-ID`, returns it on the response, and injects it into log records through context variables. Logs use stable key/value fields for `request_id`, `meeting_id`, `job_id`, and `provider` so upload jobs, worker retries, and provider failures can be correlated without parsing message text.

`ObservabilityService` keeps process-local counters for request status codes and provider operations. Provider operation metrics are grouped by `operation` and `provider`, tracking count, error count, and latency aggregates for upload ASR, live ASR startup/fallback, translation, analysis, summary, and rolling summary paths. The counters are intentionally in memory and reset on backend restart.

`GET /api/diagnostics` returns service uptime, request counters, provider operation counters, configured provider status, and a SQLite upload queue summary. The queue summary includes status counts, eligible queued jobs, delayed retries, processing jobs, stale processing claims, oldest queued age, and jobs with recorded last errors. Diagnostics do not include secrets, transcript text, absolute audio paths, or queue payload paths.

## 11. Tests And CI

Backend tests use pytest and must run through `backend/.venv`. Existing coverage includes:

- summary parsing and action item extraction behavior
- diarization assignment behavior
- live WebSocket workflow
- upload workflow
- history persistence and migration
- edit/delete audit history persistence and query behavior
- raw audio retention filename hardening
- demo provider health, WebSocket, upload, and disabled-mode behavior

The frontend uses Vitest with React Testing Library for interaction coverage. Current frontend tests cover upload status messaging, ASR provider options, upload control state, summary editing, participant analysis rendering, meeting tag normalization, audit history rendering, Markdown meeting notes export, and export formatting. `npm run build` remains the primary bundle verification step.

The Windows-first CI workflow installs backend and frontend dependencies, runs backend pytest, runs frontend tests, and builds the Vite frontend.

## 12. Demo Screenshot Refresh

Demo UI screenshots live in `docs/assets/screenshots/` and are linked from both README files. Refresh them only from demo mode so the images do not require external provider keys.

Recommended flow:

1. Start the backend with `DEMO_MODE=1`, `DEFAULT_ASR_PROVIDER=demo`, `DIARIZATION_MODE=disabled`, and a temporary local `MEETING_HISTORY_DB_PATH`.
2. Build the frontend with `cd frontend` and `npm.cmd run build` on Windows PowerShell.
3. Use the existing Electron dependency to load `frontend/dist/index.html` and capture the live demo workspace, upload completion state, and saved meeting detail.
4. Wait for UI state changes to render before capture. In automation, wait for the expected text and then wait at least two `requestAnimationFrame` ticks before calling Electron `capturePage()`.
5. Commit only the final PNG files under `docs/assets/screenshots/`. Do not commit temporary capture scripts, local SQLite files, large recordings, or dependency upgrades for screenshot capture.

If PowerShell blocks `npm.ps1`, use `npm.cmd`. Electron does not need to be upgraded for screenshot refreshes; use the dependency already present in `frontend/node_modules`.

## 13. Current Boundaries

- Live rolling summaries are provisional and not persisted; the final summary is still generated after finalize or upload completion.
- Translation supports one target language per meeting.
- Mobile background and lock-screen recording is still controlled by the operating system and browser; the frontend detects common interruptions but cannot guarantee capture while suspended.
- User-requested raw upload audio is stored separately under `RAW_AUDIO_DIR`; meeting history exposes retention metadata but not filesystem paths or download APIs.
- Upload processing uses a SQLite-backed persistent queue. FastAPI starts an embedded worker by default, and `tools/run_upload_worker.py` can process the same queue out of process. Upload jobs now have bounded retry, backoff, stale-claim recovery, and local diagnostics; external monitoring and alerting remain future work.
- Upload retry is session-local in the frontend; after a page refresh, the user must select the audio file again.
- Edit/delete audit history is local and append-only; v1 has no account actor, retention policy, or version restore UI.
- Participant-level sentiment and engagement analysis is a lightweight rollup over transcripts and explicit interaction signals; it is not a full behavioral or performance assessment.
- Demo mode is for onboarding, local smoke tests, and CI. It does not represent real provider quality.
