# Smart Meeting Assistant

语言版本：
- English: [README.md](README.md)
- 简体中文：`README-zh.md`

Smart Meeting Assistant 是一个基于 React 18 与 FastAPI 构建的浏览器端会议助手。它支持实时语音转写、实时翻译、会议总结、待办事项提取，以及会议情感与参与度分析，整体通过 WebSocket 实时工作流串联。

## 架构

- `frontend`: React 18 + TypeScript + Vite + Tailwind CSS
- `backend`: FastAPI + Uvicorn

## 功能

### 实时链路

- 浏览器麦克风采集
- 可切换实时 ASR provider：
  - 火山引擎豆包语音（默认）
  - DashScope Paraformer（`paraformer-realtime-v1`）
- 实时 transcript 展示，speaker 在 finalize 前为临时 `Unknown`
- `finalize` 后执行离线 speaker diarization，并通过 websocket 回填 speaker
- 单目标语言的实时 transcript 翻译，当前已扩充支持 10 种语言：
  - English, Spanish, French, German, Chinese
  - Japanese, Korean, Portuguese, Arabic, Hindi

### 会议总结

- 停止录音后生成最终 summary
- 结构化输出：
  - `overview`
  - `key_topics`
  - `decisions`
  - `action_items`
  - `risks`

### 会议情感与参与度分析

- 录音过程中增量更新分析结果
- `finalize` 后生成最终分析结果
- 结构化输出：
  - `overall_sentiment`
  - `engagement_level`
  - `engagement_summary`
  - 四类信号计数：
    - `agreement`
    - `disagreement`
    - `tension`
    - `hesitation`
- 在 transcript 列表中高亮情绪显著片段

### 前端体验

- 桌面端支持侧边栏与 transcript 区域拖拽调宽
- transcript 列表可滚动查看
- 双语 transcript 卡片
- 独立的 `Meeting Summary` 与 `Meeting Analysis` 面板
- 前端内置历史会议抽屉，可选择并删除已保存会议

### 历史会议

- 使用 SQLite 持久化保存会议历史
- 每次 websocket 会议连接建立后立即创建一条 `draft` 记录
- Live Transcript、实时翻译、Meeting Analysis，以及最终 Summary 都会保存下来
- 前端可从历史会议面板重新打开任意一条已保存记录进行只读查看
- 不需要的会议记录可以在历史面板中永久删除

### 上传音频转写

- `POST /api/transcribe`
- `POST /api/transcribe/batch`

上传音频会先通过 `ffmpeg` 标准化，再进行转写。
如果启用了离线 diarization，上传转写也会返回最终 speaker 标签。

## 项目结构

```text
smart-meeting-assistant/
├─ frontend/
├─ backend/
├─ .env.example
├─ docker-compose.yml
├─ FULL_FEATURE_TEST_SCRIPT.md
├─ README.md
└─ README-zh.md
```

## 技术栈

### 前端

- React 18
- TypeScript
- Vite
- Tailwind CSS
- Radix UI
- WebSocket
- Web Audio API

### 后端

- FastAPI
- Uvicorn
- Pydantic
- httpx
- websockets
- python-dotenv
- ffmpeg

### 外部服务

- DashScope Paraformer Realtime ASR
- DashScope Qwen-MT
- DashScope / Qwen 系列聊天模型

## 当前工作流

1. 浏览器采集麦克风音频
2. 前端将音频处理为 PCM 帧，并通过 WebSocket 发送到后端
3. 后端创建一条持久化的 `draft` 会议记录，并发送 `session_started`
4. 后端将音频流转发到当前选择的实时 ASR provider
5. 后端发送 `transcript`，并保存最新 transcript 状态
6. 后端翻译 transcript 文本，并发送 `translation`
7. 后端周期性生成情感与参与度分析，发送 `analysis`，并覆盖保存最新分析快照
8. 录音停止时，前端发送 `finalize`
9. 后端结束 ASR，关闭会话 WAV，执行离线 speaker diarization，发送 `speaker_update`、最终 `analysis` 和最终 `summary`，将会议标记为 `finalized`，然后关闭连接

## 运行要求

- Node.js 18+
- Python 3.10+
- ffmpeg
- 可用的 DashScope API Key
- 可选：用于离线 speaker diarization 的 Hugging Face Token

## 环境变量

在项目根目录创建 `.env`：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

推荐的后端配置：

```bash
DASHSCOPE_API_KEY=your-dashscope-api-key
DASHSCOPE_MODEL=qwen-plus
DASHSCOPE_ASR_MODEL=paraformer-realtime-v1
DASHSCOPE_TRANSLATION_MODEL=qwen-mt-flash
DEFAULT_ASR_PROVIDER=volcengine
VOLCENGINE_ASR_APP_KEY=your-volcengine-app-key
VOLCENGINE_ASR_ACCESS_KEY=your-volcengine-access-key
VOLCENGINE_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
VOLCENGINE_ASR_WS_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
VOLCENGINE_ASR_NOSTREAM_WS_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream
VOLCENGINE_ASR_SSD_VERSION=200
DIARIZATION_MODE=disabled
DIARIZATION_MODEL=pyannote/speaker-diarization-community-1
HUGGINGFACE_TOKEN=

PORT=8080
LOG_LEVEL=INFO
FFMPEG_BINARY=ffmpeg
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
MEETING_HISTORY_DB_PATH=data/meeting_history.sqlite3
```

### 关键变量说明

- `DASHSCOPE_API_KEY`: 用于 ASR、翻译、summary 和 meeting analysis
- `DASHSCOPE_MODEL`: 用于 summary 和 meeting analysis
- `DASHSCOPE_ASR_MODEL`: 实时 ASR 模型
- `DASHSCOPE_TRANSLATION_MODEL`: transcript 翻译模型
- `DEFAULT_ASR_PROVIDER`: 默认 ASR provider，可选 `volcengine` / `dashscope`
- `VOLCENGINE_ASR_APP_KEY`: 火山语音 `X-Api-App-Key`
- `VOLCENGINE_ASR_ACCESS_KEY`: 火山语音 `X-Api-Access-Key`
- `VOLCENGINE_ASR_RESOURCE_ID`: 火山语音资源 ID，例如 `volc.seedasr.sauc.duration`
- `VOLCENGINE_ASR_WS_URL`: 火山流式 ASR websocket 地址
- `VOLCENGINE_ASR_NOSTREAM_WS_URL`: upload 转写使用的火山 nostream websocket 地址
- `VOLCENGINE_ASR_SSD_VERSION`: 火山 speaker clustering 所需 SSD 版本
- `DIARIZATION_MODE`: 设为 `offline` 时启用 finalize 后 speaker diarization
- `DIARIZATION_MODEL`: 离线 diarization 模型名
- `HUGGINGFACE_TOKEN`: 下载 diarization 模型所需的 Hugging Face Token
- `FFMPEG_BINARY`: 上传转写接口使用的 ffmpeg 路径
- `MEETING_HISTORY_DB_PATH`: 持久化历史会议所用的 SQLite 文件路径

如果 diarization 被关闭或当前环境不可用，后端仍然会正常启动并继续处理请求，只是 speaker 会保持为 `Unknown`。

### 可选高级变量

- `DASHSCOPE_ASR_WS_URL`
- `DASHSCOPE_WORKSPACE_ID`

### 前端本地覆盖配置

如果前端需要连接到非默认后端：

```bash
cp frontend/.env.example frontend/.env.local
```

示例：

```bash
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
```

## 本地开发

### 启动后端

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Windows PowerShell：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

后端地址：

- `http://localhost:8080`

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：

- `http://localhost:5173`

## Electron 桌面客户端

第一版桌面客户端是 Windows 优先的 Electron 便携版。它只包装现有 React/Vite 前端，不内置 Python/FastAPI 后端。

使用桌面客户端前，请先单独启动后端：

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

如需指定桌面端连接的后端地址，可在 `frontend/.env.local` 中配置：

```bash
VITE_WS_BASE_URL=ws://localhost:8080
```

开发模式启动 Electron：

```powershell
cd frontend
npm install
npm run dev:electron
```

生成 Windows portable 包：

```powershell
cd frontend
npm run electron:pack
```

打包产物会生成在 `frontend/release/`。运行 portable exe 后，仍然需要确保 FastAPI 后端已经在 `localhost:8080` 或配置的后端地址上运行。

## Docker

```bash
docker-compose up --build
```

## API

### HTTP

- `GET /`
- `GET /api/health`
- `GET /api/meetings`
- `GET /api/meetings/{meeting_id}`
- `DELETE /api/meetings/{meeting_id}`
- `POST /api/transcribe`
- `POST /api/transcribe/batch`

### WebSocket

连接示例：

```text
ws://localhost:8080/ws/meeting?scene=general&target_lang=en
ws://localhost:8080/ws/meeting?scene=finance&target_lang=zh
ws://localhost:8080/ws/meeting?scene=hr&target_lang=ja
ws://localhost:8080/ws/meeting?scene=general&target_lang=en&provider=volcengine
```

支持的 websocket 事件类型：

#### `session_started`

```json
{
  "type": "session_started",
  "data": {
    "meeting_id": "1c4f8c5ef3d74f6388d48da5ef4d23a0",
    "status": "draft",
    "created_at": "2026-04-25T15:01:02.345678Z",
    "scene": "general",
    "target_lang": "en",
    "provider": "volcengine"
  }
}
```

#### `transcript`

```json
{
  "type": "transcript",
  "data": {
    "transcript_index": 0,
    "speaker": "Unknown",
    "speaker_is_final": false,
    "transcript_is_final": false,
    "text": "会议内容",
    "start": 0.0,
    "end": 1.5
  }
}
```

#### `transcript_update`

```json
{
  "type": "transcript_update",
  "data": {
    "transcript_index": 0,
    "speaker": "Speaker 1",
    "speaker_is_final": true,
    "transcript_is_final": true,
    "text": "会议内容",
    "start": 0.0,
    "end": 1.5
  }
}
```

#### `speaker_update`

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

#### `translation`

```json
{
  "type": "translation",
  "data": {
    "transcript_index": 0,
    "target_lang": "en",
    "text": "Hello everyone."
  }
}
```

#### `analysis`

```json
{
  "type": "analysis",
  "data": {
    "overall_sentiment": "mixed",
    "engagement_level": "medium",
    "engagement_summary": "The discussion shows clear disagreement with active participation.",
    "signal_counts": {
      "agreement": 2,
      "disagreement": 1,
      "tension": 1,
      "hesitation": 1
    },
    "highlights": [
      {
        "transcript_index": 4,
        "signal": "disagreement",
        "severity": "medium",
        "reason": "The speaker clearly opposes the proposal."
      }
    ]
  }
}
```

#### `summary`

```json
{
  "type": "summary",
  "data": {
    "overview": "团队回顾了周报内容，并对交付计划达成一致。会议确认了最终负责人和更新时间安排。",
    "key_topics": [
      "周报内容",
      "交付计划"
    ],
    "decisions": [
      "周五前完成周报定稿"
    ],
    "action_items": [
      {
        "task": "周五前发送报告",
        "assignee": "Speaker 1",
        "deadline": "周五前",
        "status": "pending",
        "source_excerpt": "我会在周五前发送报告。",
        "transcript_index": 3,
        "is_actionable": true,
        "confidence": 0.93,
        "owner_explicit": true,
        "deadline_explicit": true
      }
    ],
    "risks": []
  }
}
```

#### `error`

```json
{
  "type": "error",
  "data": "error message"
}
```

#### 前端发送的 `finalize`

```json
{
  "type": "finalize"
}
```

### 历史会议接口返回

#### `GET /api/meetings`

```json
[
  {
    "meeting_id": "1c4f8c5ef3d74f6388d48da5ef4d23a0",
    "status": "finalized",
    "scene": "general",
    "target_lang": "en",
    "provider": "volcengine",
    "created_at": "2026-04-25T15:01:02.345678Z",
    "updated_at": "2026-04-25T15:08:20.123456Z",
    "transcript_count": 18,
    "preview_text": "Let's finalize the launch plan and send the weekly report today."
  }
]
```

#### `GET /api/meetings/{meeting_id}`

```json
{
  "meeting_id": "1c4f8c5ef3d74f6388d48da5ef4d23a0",
  "status": "finalized",
  "scene": "general",
  "target_lang": "en",
  "provider": "volcengine",
  "created_at": "2026-04-25T15:01:02.345678Z",
  "updated_at": "2026-04-25T15:08:20.123456Z",
  "transcript_count": 18,
  "preview_text": "Let's finalize the launch plan and send the weekly report today.",
  "transcripts": [
    {
      "transcript_index": 0,
      "speaker": "Speaker 1",
      "speaker_is_final": true,
      "transcript_is_final": true,
      "text": "Let's finalize the launch plan.",
      "start": 0.0,
      "end": 1.4,
      "translated_text": "让我们敲定发布计划。",
      "translated_target_lang": "zh"
    }
  ],
  "summary": {
    "overview": "团队围绕发布计划达成一致，并明确了后续行动。",
    "key_topics": [
      "发布计划"
    ],
    "action_items": [],
    "decisions": [],
    "risks": []
  },
  "analysis": {
    "overall_sentiment": "neutral",
    "engagement_level": "medium",
    "engagement_summary": "会议整体专注，参与度稳定。",
    "signal_counts": {
      "agreement": 1,
      "disagreement": 0,
      "tension": 0,
      "hesitation": 0
    },
    "highlights": []
  }
}
```

## 会议场景

### `general` (默认)

- 常规会议讨论
- 行动项
- 决策
- 风险

### `finance`

- 财务 / 业务复盘类讨论
- 行动项
- 决策
- 风险

### `hr`

- 面试 / 招聘沟通
- 后续行动项
- 面试结论
- 风险

## 手动测试稿

- `FULL_FEATURE_TEST_SCRIPT.md`：用于一次性验证 transcript、translation、summary、analysis 的完整测试稿

## 当前限制

- 当前 speaker diarization 仍然是 finalize 后的离线能力，不是录音过程中的实时分离
- 火山 ASR 目前只替换了 ASR provider，翻译 / summary / analysis 仍然继续走 DashScope
- Summary 现在只在 `finalize` 后生成，不再在会议进行中刷新
- 实时 ASR 仍可能误识别术语和英文单词
- Summary 目前结合了模型输出和轻量规则补全
- Meeting analysis 目前结合了模型输出和轻量规则兜底，以增强中文显式情绪信号识别
- 情感与参与度分析是整场会议级别，不是参与者级别
- 移动端浏览器录音兼容性仍弱于桌面端
- 历史会议当前只保存元数据、transcript、translation、summary、analysis，不保存原始音频
- 上传音频转写接口不会写入历史会议记录

## License

MIT
