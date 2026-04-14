# Smart Meeting Assistant

实时会议助手，支持浏览器录音、实时转写、场景化总结，以及基于 WebSocket 的双向交互。

当前主架构：

- `frontend`: Vue 3 + TypeScript + Vite
- `backend`: FastAPI + Uvicorn

前端后端地址也已支持环境变量配置，不再写死在组件代码里。

## 项目结构

```text
smart-meeting-assistant/
├─ frontend/                  # Vue 3 前端
├─ backend/                   # FastAPI 后端
├─ .env.example               # 后端 / compose 环境模板
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

### 后端

- FastAPI
- Uvicorn
- Pydantic
- httpx
- python-dotenv
- ffmpeg

### 外部能力

- 阿里云 ASR：语音转写
- DashScope / Qwen：会议总结

## 核心功能

1. 浏览器采集麦克风音频并通过 WebSocket 发送到后端
2. 后端将浏览器 `webm/opus` 转换为标准 `wav`
3. 调用阿里云 ASR 获取转写结果
4. 按会话顺序推送 `transcript`
5. 按场景生成 `summary`
6. 停止录音时通过 `finalize` 确保最终 summary 先返回，再关闭连接

## 运行要求

- Node.js 18+
- Python 3.10+
- ffmpeg
- 可用的阿里云 / DashScope 凭证

## 配置文件约定

这个项目现在有两类配置文件，职责分开：

### 1. 根目录 `.env`

用途：

- 给 FastAPI 后端读取
- 给 `docker-compose` 注入
- 放 API key、ASR 凭证、后端运行参数

第一次使用：

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

示例内容：

```bash
DASHSCOPE_API_KEY=your-dashscope-api-key
DASHSCOPE_MODEL=qwen-plus

ALIYUN_ASR_APP_KEY=your-aliyun-asr-app-key
ALIYUN_ACCESS_KEY_ID=your-aliyun-access-key-id
ALIYUN_ACCESS_KEY_SECRET=your-aliyun-access-key-secret

PORT=8080
LOG_LEVEL=INFO
SUMMARY_INTERVAL=10
FFMPEG_BINARY=ffmpeg
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
```

后端会按这个顺序读取配置：

1. 项目根目录 `.env`
2. `backend/.env`
3. 系统环境变量

### 2. 前端 `frontend/.env.local`

用途：

- 只给前端使用
- 只控制前端连接哪个后端
- 不放任何 API key 或后端密钥

第一次需要自定义前端连接地址时：

```bash
cp frontend/.env.example frontend/.env.local
```

Windows PowerShell:

```powershell
Copy-Item frontend/.env.example frontend/.env.local
```

可配置项：

```bash
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
```

说明：

- `VITE_API_BASE_URL` 用于 Vite 开发代理
- `VITE_WS_BASE_URL` 用于前端 WebSocket 直连地址
- 不配置时，开发环境默认连 `localhost:8080`
- 不配置时，生产环境按当前页面 host 推导

## 最常见的使用方式

### 场景 1：本机开发，前后端都在本机

只需要配置根目录 `.env`。

前端不用额外建 `.env.local`，会默认连接 `localhost:8080`。

### 场景 2：前端本机跑，后端在远程机器

除了根目录 `.env` 之外，再新增：

- `frontend/.env.local`

把前端地址改成远程后端，例如：

```bash
VITE_API_BASE_URL=http://192.168.1.10:8080
VITE_WS_BASE_URL=ws://192.168.1.10:8080
```

### 场景 3：Docker 启动

只需要根目录 `.env`。

`docker-compose` 会直接读取它。

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

开发态下前端默认连接：

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

### WebSocket

连接地址：

```text
ws://localhost:8080/ws/meeting?scene=finance
ws://localhost:8080/ws/meeting?scene=hr
```

后端输出消息格式：

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

- 录音期间前端持续发送二进制音频块
- 停止录音时先发送 `finalize`
- 后端处理剩余音频并返回最终 `summary`
- 最终 `summary` 发送完成后，后端主动关闭连接

## 会议场景

### finance

- 财务对账
- 待办事项提取
- 决策点提取
- 风险项提取

### hr

- 招聘 / 面试场景
- 后续待办提取
- 面试结论提取
- 风险项提取

## 注意事项

- 根目录 `.env` 已加入 `.gitignore`，不会提交到仓库
- 前端 `.env.local` 也已忽略，不会提交到仓库
- `.env.example` 和 `frontend/.env.example` 都只放模板，不要写真实密钥
- 当前 `speaker` 仍是占位逻辑，不是真正的 diarization
- 阿里云 ASR token 逻辑已抽象，但仍建议后续补正式 token / STS 方案

## License

MIT
