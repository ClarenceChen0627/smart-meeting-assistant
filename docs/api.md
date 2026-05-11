# API Reference

Language:
- English: `api.md`
- 简体中文: [zh/api.md](zh/api.md)

Backend base URL: `http://localhost:8080`.

## Health

`GET /api/health`

Returns service metadata, `demoMode`, and provider availability.

```json
{
  "status": "UP",
  "service": "Smart Meeting Assistant Backend",
  "version": "2.0.0",
  "timestamp": "2026-04-25T15:01:02.345678+00:00",
  "demoMode": true,
  "providers": {
    "asrConfigured": false,
    "llmConfigured": false,
    "availableAsrProviders": ["demo"],
    "asrProviderStatuses": [
      { "provider": "dashscope", "configured": false },
      { "provider": "volcengine", "configured": false },
      { "provider": "demo", "configured": true }
    ]
  }
}
```

## Diagnostics

`GET /api/diagnostics`

Returns a local runtime diagnostics snapshot for self-hosted troubleshooting. Metrics are process-local and reset when the backend restarts. The response does not include secrets, transcript text, audio paths, or local payload paths.

```json
{
  "service": {
    "name": "Smart Meeting Assistant Backend",
    "version": "2.0.0",
    "demoMode": true,
    "startedAt": "2026-05-11T08:00:00Z",
    "uptimeSeconds": 123.45,
    "timestamp": "2026-05-11T08:02:03Z"
  },
  "requests": {
    "total": 42,
    "byStatus": { "200": 40, "202": 2 }
  },
  "providers": {
    "statuses": [{ "provider": "demo", "configured": true }],
    "operations": [
      {
        "operation": "upload_asr",
        "provider": "demo",
        "count": 2,
        "error_count": 0,
        "average_latency_seconds": 0.01,
        "max_latency_seconds": 0.02,
        "total_latency_seconds": 0.02
      }
    ]
  },
  "uploadQueue": {
    "byStatus": { "queued": 1, "completed": 2 },
    "eligibleQueued": 1,
    "delayedRetry": 0,
    "processing": 0,
    "staleProcessing": 0,
    "oldestQueuedAgeSeconds": 12.3,
    "lastErrorCount": 0
  }
}
```

Every HTTP response includes an `X-Request-ID` header. Clients may send the same header to reuse a request id in backend logs.

## HTTP Endpoints

- `GET /`
- `GET /api/health`
- `GET /api/diagnostics`
- `GET /api/glossary/terms`
- `POST /api/glossary/terms`
- `PATCH /api/glossary/terms/{term_id}`
- `DELETE /api/glossary/terms/{term_id}`
- `GET /api/meetings`
- `GET /api/meetings/{meeting_id}`
- `PATCH /api/meetings/{meeting_id}/title`
- `PATCH /api/meetings/{meeting_id}/summary`
- `PATCH /api/meetings/{meeting_id}/speakers`
- `PATCH /api/meetings/{meeting_id}/action-items/{action_item_index}`
- `DELETE /api/meetings/{meeting_id}`
- `POST /api/meetings/upload`
- `POST /api/transcribe`
- `POST /api/transcribe/batch`

`POST /api/meetings/upload` is the product upload workflow. `POST /api/transcribe` and `POST /api/transcribe/batch` are transcript-only utility/debug endpoints.

## Glossary Terms

Global glossary terms are stored in the local SQLite database configured by `MEETING_HISTORY_DB_PATH`. Live and upload meetings automatically merge saved terms with per-meeting `glossary_terms` and `CUSTOM_GLOSSARY_TERMS`.

`GET /api/glossary/terms`

Returns saved terms:

```json
[
  {
    "id": "d2e4f6",
    "term": "queue wen",
    "replacement": "Qwen",
    "note": "DashScope model family",
    "created_at": "2026-05-09T01:00:00Z",
    "updated_at": "2026-05-09T01:00:00Z"
  }
]
```

`POST /api/glossary/terms`

```json
{
  "term": "queue wen",
  "replacement": "Qwen",
  "note": "DashScope model family"
}
```

`PATCH /api/glossary/terms/{term_id}` accepts any subset of `term`, `replacement`, and `note`. `DELETE /api/glossary/terms/{term_id}` removes a saved term.

Duplicate terms are rejected case-insensitively with `409 Conflict`. Per-meeting terms take precedence when a saved term uses the same `term`.

## Speaker Corrections

`PATCH /api/meetings/{meeting_id}/speakers`

Renames or merges speaker labels for saved meetings. This endpoint is allowed only after a meeting is `finalized` or `failed`; `draft` live sessions and `processing` uploads return `409 Conflict`.

```json
{
  "speaker_updates": [
    { "from": "Speaker 1", "to": "Alice" },
    { "from": "Speaker 3", "to": "Alice" },
    { "from": "Speaker 2", "to": "Bob" }
  ]
}
```

Multiple `from` labels can point to the same `to` label to merge speakers. The response is the updated `MeetingRecord`. The backend updates transcript speaker labels, exact action item assignee references, and participant-level analysis rollups. It does not rerun LLM summary or analysis generation.

## Upload Meeting

`POST /api/meetings/upload`

Multipart fields:

- `file`: one meeting audio file.
- `scene`: `general`, `finance`, or `hr`.
- `target_lang`: optional translation target such as `en`, `zh`, `ja`, or `es`.
- `provider`: optional ASR provider: `volcengine`, `dashscope`, or `demo`.
- `retain_raw_audio`: optional boolean. When true and server retention is enabled, the original upload is stored under `RAW_AUDIO_DIR`.
- `glossary_terms`: optional custom terminology. Use one term per line or entries like `queue wen=>Qwen`.

Returns `202 Accepted` with a `MeetingRecord`. The frontend should poll `GET /api/meetings/{meeting_id}` until `status` is `finalized` or `failed`.

## WebSocket

Connect to:

```text
ws://localhost:8080/ws/meeting?scene=general&target_lang=en&provider=volcengine
ws://localhost:8080/ws/meeting?scene=general&target_lang=ja&provider=demo
ws://localhost:8080/ws/meeting?scene=general&provider=dashscope&glossary_terms=queue%20wen%3D%3EQwen
```

The client sends raw PCM audio bytes. To finish a live meeting, send:

```json
{ "type": "finalize" }
```

## WebSocket Event Types

### `session_started`

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

### `transcript` / `transcript_update`

```json
{
  "type": "transcript",
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

### `speaker_update`

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

### `translation`

```json
{
  "type": "translation",
  "data": {
    "transcript_index": 0,
    "target_lang": "ja",
    "text": "こんにちは。"
  }
}
```

### `analysis`

```json
{
  "type": "analysis",
  "data": {
    "overall_sentiment": "mixed",
    "engagement_level": "medium",
    "engagement_summary": "The discussion shows active participation.",
    "signal_counts": {
      "agreement": 1,
      "disagreement": 0,
      "tension": 1,
      "hesitation": 0
    },
    "highlights": [],
    "participants": [
      {
        "speaker": "Speaker 1",
        "transcript_count": 4,
        "speaking_time_seconds": 18.2,
        "signal_counts": {
          "agreement": 1,
          "disagreement": 0,
          "tension": 0,
          "hesitation": 0
        },
        "sentiment": "positive",
        "engagement_level": "high",
        "engagement_summary": "Speaker 1 contributed 4 utterances with 1 interaction signals."
      }
    ]
  }
}
```

### `rolling_summary`

`rolling_summary` is a provisional live-only summary. It reuses the `MeetingSummary` shape, starts after at least three final transcript rows, and is throttled to every three new final rows with at least 60 seconds between requests. It is not saved to `summary_json`; the final `summary` event remains authoritative.

```json
{
  "type": "rolling_summary",
  "data": {
    "title": "Launch Plan Review",
    "overview": "The team is aligning on the launch plan so far.",
    "key_topics": ["Launch plan"],
    "decisions": [],
    "action_items": [],
    "risks": []
  }
}
```

### `summary`

The final `summary` event is emitted after live `finalize` or upload completion and is persisted to the meeting record.

```json
{
  "type": "summary",
  "data": {
    "title": "Launch Plan Review",
    "overview": "The team aligned on the launch plan and next steps.",
    "key_topics": ["Launch plan"],
    "decisions": ["Proceed with the launch plan"],
    "action_items": [],
    "risks": []
  }
}
```

### `error`

```json
{
  "type": "error",
  "data": "error message"
}
```

## Meeting Record Shape

`GET /api/meetings` returns list items without full transcript rows. `GET /api/meetings/{meeting_id}` returns the full `MeetingRecord`, including transcripts, summary, and analysis.

Important fields:

- `status`: `draft`, `processing`, `finalized`, or `failed`.
- `source_type`: `live` or `upload`.
- `provider`: `volcengine`, `dashscope`, or `demo`.
- `processing_stage`: `transcribing`, `translating`, `analyzing`, `summarizing`, or `null`.
- `raw_audio_retained`: true when the original upload was retained.
- `raw_audio_filename`, `raw_audio_content_type`, `raw_audio_size_bytes`: retained audio metadata; the server does not expose the filesystem path.
- `glossary_terms`: custom terminology terms saved with the meeting record.
- `summary_manually_edited`: true after the user edits summary fields.
- `title_manually_edited`: true after the user renames a saved meeting.
