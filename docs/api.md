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

## HTTP Endpoints

- `GET /`
- `GET /api/health`
- `GET /api/meetings`
- `GET /api/meetings/{meeting_id}`
- `PATCH /api/meetings/{meeting_id}/title`
- `PATCH /api/meetings/{meeting_id}/summary`
- `PATCH /api/meetings/{meeting_id}/action-items/{action_item_index}`
- `DELETE /api/meetings/{meeting_id}`
- `POST /api/meetings/upload`
- `POST /api/transcribe`
- `POST /api/transcribe/batch`

`POST /api/meetings/upload` is the product upload workflow. `POST /api/transcribe` and `POST /api/transcribe/batch` are transcript-only utility/debug endpoints.

## Upload Meeting

`POST /api/meetings/upload`

Multipart fields:

- `file`: one meeting audio file.
- `scene`: `general`, `finance`, or `hr`.
- `target_lang`: optional translation target such as `en`, `zh`, `ja`, or `es`.
- `provider`: optional ASR provider: `volcengine`, `dashscope`, or `demo`.

Returns `202 Accepted` with a `MeetingRecord`. The frontend should poll `GET /api/meetings/{meeting_id}` until `status` is `finalized` or `failed`.

## WebSocket

Connect to:

```text
ws://localhost:8080/ws/meeting?scene=general&target_lang=en&provider=volcengine
ws://localhost:8080/ws/meeting?scene=general&target_lang=ja&provider=demo
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
    "highlights": []
  }
}
```

### `summary`

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
- `summary_manually_edited`: true after the user edits summary fields.
- `title_manually_edited`: true after the user renames a saved meeting.
