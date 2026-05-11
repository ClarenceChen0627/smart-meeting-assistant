# API Reference

Language:
- English: [../api.md](../api.md)
- 简体中文: `api.md`

后端默认地址：`http://localhost:8080`。

## Authentication

当 `API_ACCESS_TOKEN` 为空时，本地开发行为保持不变。设置后，除 `/` 和 `/api/health` 外，其他接口都需要以下任一 header：

```http
Authorization: Bearer <token>
```

或：

```http
X-API-Token: <token>
```

浏览器 WebSocket 连接需要通过 `access_token=<token>` 传递 token，因为浏览器 WebSocket API 不能设置自定义 header。

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

## Diagnostics

`GET /api/diagnostics`

返回本地运行诊断快照，用于自部署排障。指标只保存在当前进程内，后端重启后清零。响应不会包含 secret、转写文本、音频路径或本地 payload 路径。

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

所有 HTTP 响应都会带 `X-Request-ID` header。客户端也可以主动传入同名 header，让后端日志复用该 request id。

## HTTP Endpoints

- `GET /`
- `GET /api/health`
- `GET /api/diagnostics`
- `GET /api/glossary/terms`
- `POST /api/glossary/terms`
- `PATCH /api/glossary/terms/{term_id}`
- `DELETE /api/glossary/terms/{term_id}`
- `GET /api/audit-events`
- `GET /api/meetings?q=&status=&source_type=&provider=&scene=&favorite=&archived=&tag=`
- `GET /api/meetings/{meeting_id}`
- `GET /api/meetings/{meeting_id}/audit-events`
- `PATCH /api/meetings/{meeting_id}/metadata`
- `PATCH /api/meetings/{meeting_id}/title`
- `PATCH /api/meetings/{meeting_id}/summary`
- `PATCH /api/meetings/{meeting_id}/speakers`
- `PATCH /api/meetings/{meeting_id}/action-items/{action_item_index}`
- `DELETE /api/meetings/{meeting_id}`
- `POST /api/meetings/upload`
- `POST /api/transcribe`
- `POST /api/transcribe/batch`

`POST /api/meetings/upload` 是产品上传流程。`POST /api/transcribe` 和 `POST /api/transcribe/batch` 是只返回转写结果的工具/调试接口。

## 术语表

全局术语表保存在 `MEETING_HISTORY_DB_PATH` 指向的本地 SQLite 数据库中。live 和 upload 会议会自动合并已保存术语、单场会议传入的 `glossary_terms` 和 `CUSTOM_GLOSSARY_TERMS`。

`GET /api/glossary/terms`

返回已保存术语：

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

`PATCH /api/glossary/terms/{term_id}` 可更新 `term`、`replacement`、`note` 的任意子集。`DELETE /api/glossary/terms/{term_id}` 删除已保存术语。

重复术语按大小写不敏感方式返回 `409 Conflict`。如果单场会议术语和已保存术语的 `term` 相同，单场会议术语优先。

## 审计事件

成功提交的人工编辑会写入 `MEETING_HISTORY_DB_PATH` 指向的本地 SQLite 数据库。审计范围包括会议标题编辑、summary 编辑、action item 状态编辑、speaker 修正，以及全局术语的新增、更新和删除。v1 不审计 ASR/LLM 自动生成内容、上传 worker 状态流转或会议删除。

`GET /api/meetings/{meeting_id}/audit-events`

返回指定会议最近的审计事件，按时间倒序排列。可选 `limit` query 参数默认 100，最大 500。

```json
[
  {
    "id": "a1b2c3",
    "scope": "meeting",
    "meeting_id": "meeting-1",
    "entity_type": "speaker",
    "entity_id": "meeting-1",
    "action": "update",
    "field_path": "transcripts.speaker",
    "before": { "speakers": ["Speaker 1", "Speaker 2"] },
    "after": { "speakers": ["Alice", "Speaker 2"] },
    "metadata": {
      "speaker_updates": [{ "from": "Speaker 1", "to": "Alice" }],
      "affected_transcript_count": 3,
      "merge_count": 0
    },
    "created_at": "2026-05-11T08:00:00Z"
  }
]
```

`GET /api/audit-events?scope=global&entity_type=glossary_term`

返回全局审计事件，主要用于本地排障和后续 UI 扩展。全局术语事件使用 `scope: "global"`，并且 `meeting_id` 为 `null`。

## Speaker 修正

`PATCH /api/meetings/{meeting_id}/speakers`

用于重命名或合并已保存会议的 speaker label。只允许在会议状态为 `finalized` 或 `failed` 后调用；`draft` 实时会议和 `processing` 上传会议会返回 `409 Conflict`。

```json
{
  "speaker_updates": [
    { "from": "Speaker 1", "to": "Alice" },
    { "from": "Speaker 3", "to": "Alice" },
    { "from": "Speaker 2", "to": "Bob" }
  ]
}
```

多个 `from` 指向同一个 `to` 即表示合并 speaker。接口返回更新后的 `MeetingRecord`。后端会写回 transcript speaker label，同步精确匹配的 action item assignee，并重建参与者级 analysis 汇总；不会自动重跑 LLM 总结或分析。

## Upload Meeting

`POST /api/meetings/upload`

Multipart 字段：

- `file`：一个会议音频文件。
- `scene`：`general`、`finance` 或 `hr`。
- `target_lang`：可选翻译目标语言，例如 `en`、`zh`、`ja` 或 `es`。
- `provider`：可选 ASR provider：`volcengine`、`dashscope` 或 `demo`。
- `retain_raw_audio`：可选布尔值。为 true 且服务端开启留存时，原始上传会保存到 `RAW_AUDIO_DIR`。
- `glossary_terms`：可选自定义术语。每行一个术语，或使用 `queue wen=>Qwen` 形式。

接口返回 `202 Accepted` 和一个 `MeetingRecord`。前端应轮询 `GET /api/meetings/{meeting_id}`，直到 `status` 变为 `finalized` 或 `failed`。

当上传超过 `MAX_UPLOAD_BYTES` 时返回 `413`；当 content type 不在 `ALLOWED_UPLOAD_CONTENT_TYPES` 中时返回 `415`。

## WebSocket

连接示例：

```text
ws://localhost:8080/ws/meeting?scene=general&target_lang=en&provider=volcengine
ws://localhost:8080/ws/meeting?scene=general&target_lang=ja&provider=demo
ws://localhost:8080/ws/meeting?scene=general&provider=dashscope&glossary_terms=queue%20wen%3D%3EQwen
ws://localhost:8080/ws/meeting?scene=general&provider=demo&access_token=your-token
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

### `rolling_summary`

`rolling_summary` 是仅用于 live 会中的临时滚动摘要。它复用 `MeetingSummary` 数据结构，在至少 3 条 final transcript 后开始生成，之后每新增 3 条 final transcript 且距离上次请求至少 60 秒才会再次触发。它不会写入 `summary_json`；最终 `summary` 事件仍然是权威结果。

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

最终 `summary` 事件在 live `finalize` 后或上传处理完成后发送，并写入会议记录。

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
- `raw_audio_retained`：原始上传音频是否已留存。
- `raw_audio_filename`、`raw_audio_content_type`、`raw_audio_size_bytes`：留存音频元数据；服务端不暴露文件系统路径。
- `glossary_terms`：本次会议实际使用并保存的术语。
- `summary_manually_edited`：用户编辑 summary 字段后为 true。
- `title_manually_edited`：用户重命名保存会议后为 true。
- `favorite`：用户是否将会议标记为重要。
- `archived`：会议是否从默认 active 历史视图中隐藏。
- `tags`：用户维护的会议标签，用于筛选和整理。

`PATCH /api/meetings/{meeting_id}/metadata`

更新轻量会议整理元数据：

```json
{
  "favorite": true,
  "archived": false,
  "tags": ["Customer", "Q2"]
}
```
