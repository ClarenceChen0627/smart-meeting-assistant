# Smart Meeting Assistant

实时会议助手，支持浏览器实时录音、实时转写、实时译文展示、场景化总结，以及基于 WebSocket 的双向交互。

当前主架构：

- `frontend`: Vue 3 + TypeScript + Vite
- `backend`: FastAPI + Uvicorn

## 项目结构

```text
smart-meeting-assistant/
├─ frontend/                  # Vue 3 前端
├─ backend/                   # FastAPI 后端
├─ .env.example               # 后端 / docker-compose 环境变量模板
├─ docker-compose.yml
└─ README.md
```

## 技术栈

### 前端

- Vue 3
- TypeScript
- Vite
- Element Plus
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

### 外部能力

- DashScope Paraformer Realtime ASR: 实时语音转写
- DashScope Qwen-MT: transcript 文本翻译
- DashScope / Qwen: 会议总结

## 当前工作流

1. 前端通过麦克风采集音频
2. 前端将音频转换为 `16kHz / 单声道 / PCM16`，通过 WebSocket 发送到后端
3. 后端将 PCM 音频流转发到 DashScope `paraformer-realtime-v1`
4. 后端将转写结果实时推送为 `transcript`
5. 后端将 transcript 文本实时翻译为目标语言，并推送为 `translation`
6. 后端按场景生成 `summary`
7. 停止录音时，前端发送 `finalize`，后端返回最终 `summary` 后关闭连接

说明：

- 当前会议实时转写不再使用阿里云 NLS `FlashRecognizer`
- `ffmpeg` 现在主要用于 `/api/transcribe` 上传文件接口的音频转码

## 运行要求

- Node.js 18+
- Python 3.10+
- ffmpeg
- 可用的 DashScope API Key

## 环境变量

根目录 `.env` 用于后端与 `docker-compose`。

首次使用：

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

推荐配置：

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

关键变量说明：

- `DASHSCOPE_API_KEY`: 百炼 API Key，同时用于实时 ASR 和总结
- `DASHSCOPE_MODEL`: 文本总结模型，例如 `qwen-plus-2025-01-25`
- `DASHSCOPE_ASR_MODEL`: 实时 ASR 模型，当前推荐 `paraformer-realtime-v1`
- `DASHSCOPE_TRANSLATION_MODEL`: 文本翻译模型，当前默认 `qwen-mt-flash`
- `SUMMARY_INTERVAL`: 每累计多少条 transcript 触发一次中途 summary
- `FFMPEG_BINARY`: `ffmpeg` 可执行文件路径；如果系统 PATH 已配置，可保持为 `ffmpeg`
- `AUDIO_SAMPLE_RATE`: 当前默认 `16000`
- `AUDIO_CHANNELS`: 当前默认 `1`

可选高级变量：

- `DASHSCOPE_ASR_WS_URL`: DashScope ASR WebSocket 地址
- `DASHSCOPE_WORKSPACE_ID`: 指定 DashScope workspace 时使用

### 前端环境变量

如果前端需要连接非默认后端地址，可在 `frontend/.env.local` 中配置：

```bash
cp frontend/.env.example frontend/.env.local
```

Windows PowerShell:

```powershell
Copy-Item frontend/.env.example frontend/.env.local
```

示例：

```bash
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
```

## 本地开发

### 1. 启动后端

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

后端地址：

- `http://localhost:8080`

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：

- `http://localhost:3000`

开发环境下前端默认连接：

- `ws://localhost:8080/ws/meeting`

## Docker 启动

```bash
docker-compose up --build
```

启动后：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8080`

## API 说明

### HTTP

- `GET /`
- `GET /api/health`
- `POST /api/transcribe`
- `POST /api/transcribe/batch`

说明：

- `/api/transcribe` 和 `/api/transcribe/batch` 仍会通过 `ffmpeg` 将上传音频转换为标准 `wav`
- 转写后仍统一走 DashScope ASR

### WebSocket

连接地址：

```text
ws://localhost:8080/ws/meeting?scene=finance
ws://localhost:8080/ws/meeting?scene=hr
```

后端推送消息：

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

```json
{
  "type": "error",
  "data": "error message"
}
```

停止录音时前端发送：

```json
{
  "type": "finalize"
}
```

行为约定：

- 录音期间前端持续发送 PCM 音频二进制帧
- 连接建立时可通过 `target_lang` 指定目标语言，当前支持 `en` / `ja` / `ko`
- 停止录音时先发送 `finalize`
- 后端结束实时 ASR，会返回最终 `summary`
- 最终 `summary` 发送完成后，后端主动关闭 WebSocket

## 会议场景

### finance

- 财务会议
- 待办事项提取
- 决策点提取
- 风险项提取

### hr

- 招聘 / 面试场景
- 后续待办提取
- 面试结论提取
- 风险项提取

## 当前限制

- `speaker` 仍然是占位逻辑，不是真正的 diarization
- 实时 ASR 对术语和英文单词仍可能出现误识别
- Summary 会结合模型输出和简单规则补全，但仍不是完整的会议纪要系统

## License

MIT
