# API Reference

Language:
- English: [../api.md](../api.md)
- 简体中文: `api.md`

后端默认地址：`http://localhost:8080`。

## Health

`GET /api/health`

返回服务元信息、`demoMode` 和 provider 可用性。

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

`POST /api/meetings/upload` 是产品上传流程。`POST /api/transcribe` 和 `POST /api/transcribe/batch` 是只返回转写结果的工具/调试接口。

## Upload Meeting

`POST /api/meetings/upload`

Multipart 字段：

- `file`：一个会议音频文件。
- `scene`：`general`、`finance` 或 `hr`。
- `target_lang`：可选翻译目标语言，例如 `en`、`zh`、`ja` 或 `es`。
- `provider`：可选 ASR provider：`volcengine`、`dashscope` 或 `demo`。

接口返回 `202 Accepted` 和一个 `MeetingRecord`。前端应轮询 `GET /api/meetings/{meeting_id}`，直到 `status` 变为 `finalized` 或 `failed`。

## WebSocket

连接示例：

```text
ws://localhost:8080/ws/meeting?scene=general&target_lang=en&provider=volcengine
ws://localhost:8080/ws/meeting?scene=general&target_lang=ja&provider=demo
```

客户端发送原始 PCM 音频 bytes。结束实时会议时发送：

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

`GET /api/meetings` 返回不带完整 transcript rows 的列表项。`GET /api/meetings/{meeting_id}` 返回完整 `MeetingRecord`，包含 transcripts、summary 和 analysis。

重要字段：

- `status`：`draft`、`processing`、`finalized` 或 `failed`。
- `source_type`：`live` 或 `upload`。
- `provider`：`volcengine`、`dashscope` 或 `demo`。
- `processing_stage`：`transcribing`、`translating`、`analyzing`、`summarizing` 或 `null`。
- `summary_manually_edited`：用户编辑 summary 字段后为 true。
- `title_manually_edited`：用户重命名保存会议后为 true。
