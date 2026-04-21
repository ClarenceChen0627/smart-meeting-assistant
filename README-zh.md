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
- 基于 DashScope Paraformer 的实时语音识别（`paraformer-realtime-v1`）
- 实时 transcript 展示
- 单目标语言的实时 transcript 翻译，当前支持：
  - English
  - Japanese
  - Korean

### 会议总结

- 停止录音后生成最终 summary
- 结构化输出：
  - `todos`
  - `decisions`
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

### 上传音频转写

- `POST /api/transcribe`
- `POST /api/transcribe/batch`

上传音频会先通过 `ffmpeg` 标准化，再进行转写。

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
3. 后端将音频流转发到 DashScope 实时 ASR
4. 后端发送 `transcript`
5. 后端翻译 transcript 文本，并发送 `translation`
6. 后端周期性生成情感与参与度分析，并发送 `analysis`
7. 录音停止时，前端发送 `finalize`
8. 后端结束 ASR，发送最终 `analysis` 和最终 `summary`，然后关闭连接

## 运行要求

- Node.js 18+
- Python 3.10+
- ffmpeg
- 可用的 DashScope API Key

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

PORT=8080
LOG_LEVEL=INFO
SUMMARY_INTERVAL=10
FFMPEG_BINARY=ffmpeg
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
```

### 关键变量说明

- `DASHSCOPE_API_KEY`: 用于 ASR、翻译、summary 和 meeting analysis
- `DASHSCOPE_MODEL`: 用于 summary 和 meeting analysis
- `DASHSCOPE_ASR_MODEL`: 实时 ASR 模型
- `DASHSCOPE_TRANSLATION_MODEL`: transcript 翻译模型
- `SUMMARY_INTERVAL`: 中途生成 summary 的 transcript 数量阈值
- `FFMPEG_BINARY`: 上传转写接口使用的 ffmpeg 路径

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

- `https://localhost:5173`

## Docker

```bash
docker-compose up --build
```

## API

### HTTP

- `GET /`
- `GET /api/health`
- `POST /api/transcribe`
- `POST /api/transcribe/batch`

### WebSocket

连接示例：

```text
ws://localhost:8080/ws/meeting?scene=finance&target_lang=en
ws://localhost:8080/ws/meeting?scene=hr&target_lang=ja
```

支持的 websocket 事件类型：

#### `transcript`

```json
{
  "type": "transcript",
  "data": {
    "speaker": "Speaker_A",
    "text": "会议内容",
    "start": 0.0,
    "end": 1.5
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
    "todos": [],
    "decisions": [],
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

## 会议场景

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

- `speaker` 仍然是占位逻辑，不是真正的 diarization
- 实时 ASR 仍可能误识别术语和英文单词
- Summary 目前结合了模型输出和轻量规则补全
- Meeting analysis 目前结合了模型输出和轻量规则兜底，以增强中文显式情绪信号识别
- 情感与参与度分析是整场会议级别，不是参与者级别
- 移动端浏览器录音兼容性仍弱于桌面端

## License

MIT
