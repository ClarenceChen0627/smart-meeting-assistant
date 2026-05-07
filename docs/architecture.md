# Architecture

Language:
- English: `architecture.md`
- 简体中文: [zh/architecture.md](zh/architecture.md)

Smart Meeting Assistant has a React/Vite frontend, a FastAPI backend, provider clients for ASR and LLM workflows, and SQLite-backed meeting history.

## System Overview

```mermaid
flowchart LR
  Browser[Browser or Electron client] -->|HTTP| API[FastAPI HTTP API]
  Browser -->|WebSocket PCM audio| WS[FastAPI /ws/meeting]
  API --> History[(SQLite meeting history)]
  WS --> Session[SessionManager]
  Session --> ASR[ASR provider service]
  ASR --> DemoASR[Demo ASR]
  ASR --> Volcengine[Volcengine Doubao ASR]
  ASR --> DashScopeASR[DashScope Paraformer ASR]
  Session --> Translation[Translation service]
  Session --> Analysis[Meeting analysis service]
  Session --> Summary[Summary service]
  Translation --> LLM[DashScope or demo LLM client]
  Analysis --> LLM
  Summary --> LLM
  Session --> History
```

## Live Meeting Flow

```mermaid
sequenceDiagram
  participant UI as Frontend
  participant WS as /ws/meeting
  participant SM as SessionManager
  participant ASR as ASR provider
  participant AI as Translation/Summary/Analysis
  participant DB as Meeting history

  UI->>WS: connect(scene, target_lang, provider)
  WS->>SM: create session
  SM->>DB: create draft meeting
  SM-->>UI: session_started
  UI->>WS: PCM audio chunks
  SM->>ASR: stream audio
  ASR-->>SM: transcript segments
  SM->>DB: upsert transcripts
  SM-->>UI: transcript / transcript_update
  SM->>AI: translate and analyze incrementally
  AI-->>UI: translation / analysis
  UI->>WS: {"type":"finalize"}
  SM->>AI: final analysis and summary
  SM->>DB: persist final outputs
  SM-->>UI: analysis / summary
```

## Upload Meeting Flow

```mermaid
sequenceDiagram
  participant UI as Frontend
  participant API as POST /api/meetings/upload
  participant Worker as UploadMeetingService
  participant ASR as ASR provider
  participant AI as Translation/Summary/Analysis
  participant DB as Meeting history

  UI->>API: upload audio + scene + target_lang + provider
  API->>DB: create processing upload record
  API-->>UI: 202 MeetingRecord
  API->>Worker: process in background
  Worker->>ASR: transcribe audio
  Worker->>DB: persist transcript rows
  Worker->>AI: translate, analyze, summarize
  Worker->>DB: persist outputs and finalize
  UI->>API: poll GET /api/meetings/{id}
```

## Meeting State

```mermaid
stateDiagram-v2
  [*] --> draft: live websocket created
  [*] --> processing: upload accepted
  draft --> finalized: live finalize completes
  draft --> draft: disconnect before finalize
  processing --> finalized: upload processing succeeds
  processing --> failed: upload processing fails
  finalized --> [*]
  failed --> [*]
```

## Important Boundaries

- `backend/app/clients/` owns provider-specific network clients and protocol adapters.
- `backend/app/services/asr_provider_service.py` chooses the active ASR provider and fallback order.
- `backend/app/services/session_manager.py` owns live WebSocket session state and persistence.
- `backend/app/services/upload_meeting_service.py` owns uploaded-audio processing.
- `frontend/src/app/` owns the main workspace and meeting panels.
