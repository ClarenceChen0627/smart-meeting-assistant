# Configuration

Language:
- English: [../configuration.md](../configuration.md)
- 简体中文: `configuration.md`

本地开发前先复制根目录后端环境变量文件：

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

前端 URL 覆盖配置放在 `frontend/.env.local`，从 `frontend/.env.example` 复制。

## Minimal Configuration Matrix

| Workflow | Required backend variables | Notes |
| --- | --- | --- |
| Demo mode | `DEMO_MODE=1` | 不需要外部 AI key。用于本地 smoke test 和 CI。 |
| Browser frontend | 后端不是 `localhost:8080` 时配置 `VITE_API_BASE_URL`、`VITE_WS_BASE_URL` | 放在 `frontend/.env.local`。 |
| Local backend | `PORT`、`LOG_LEVEL`、`MEETING_HISTORY_DB_PATH` | 默认值足够启动后端。 |
| Realtime Volcengine ASR | `DEFAULT_ASR_PROVIDER=volcengine`、`VOLCENGINE_ASR_APP_KEY`、`VOLCENGINE_ASR_ACCESS_KEY`、`VOLCENGINE_ASR_RESOURCE_ID` | Volcengine 可返回原生 speaker clustering。 |
| Realtime DashScope ASR | `DEFAULT_ASR_PROVIDER=dashscope`、`DASHSCOPE_API_KEY`、`DASHSCOPE_ASR_MODEL` | DashScope Paraformer 实时 ASR 所需。 |
| Translation, summary, analysis | `DASHSCOPE_API_KEY`、`DASHSCOPE_MODEL`、`DASHSCOPE_TRANSLATION_MODEL` | 翻译、总结和会议分析使用。 |
| Upload meetings | 一个已配置的 ASR provider，加 `FFMPEG_BINARY` | `DEMO_MODE=1` 的 demo upload 会跳过外部 ASR 和 ffmpeg conversion。 |
| Offline diarization | DashScope ASR 加 `DIARIZATION_MODE=offline`、`HUGGINGFACE_TOKEN`、`DIARIZATION_MODEL` | 在 finalize 或上传转写后运行。 |
| Hybrid diarization | DashScope ASR 加 `DIARIZATION_MODE=hybrid`、`DIART_PYTHON_PATH` | diart 实时 speaker 更新是临时结果，最终以 pyannote 为准。 |
| Electron client | 正在运行的后端；如果后端 URL 自定义，则配置 `frontend/.env.local` | Electron 只包装 Vite 前端，不启动 FastAPI。 |

## Demo Mode

设置：

```env
DEMO_MODE=1
DEFAULT_ASR_PROVIDER=demo
DIARIZATION_MODE=disabled
```

Demo mode 提供确定性的本地 ASR、翻译、总结和分析结果，用于 onboarding、开发、文档 smoke test 和 CI。它不代表真实模型质量。

当 `DEMO_MODE=1` 时，WebSocket 和上传流程都可以使用 `provider=demo`。当 `DEMO_MODE=0` 时，显式请求 `provider=demo` 会停留在 demo provider 并报告未配置，而不是静默伪装成真实 provider。

## Backend Variables

- `PORT`: FastAPI 端口，默认 `8080`。
- `LOG_LEVEL`: 后端日志等级，默认 `INFO`。
- `DEMO_MODE`: 设置为 `1`、`true`、`yes` 或 `on` 时启用本地 demo provider。
- `FFMPEG_BINARY`: 非 demo 上传时使用的 ffmpeg 可执行文件。
- `AUDIO_SAMPLE_RATE`: PCM 采样率，默认 `16000`。
- `AUDIO_CHANNELS`: 音频声道数，默认 `1`。
- `MEETING_HISTORY_DB_PATH`: SQLite 会议历史路径。
- `DEFAULT_ASR_PROVIDER`: `volcengine`、`dashscope` 或 `demo`。
- `DASHSCOPE_API_KEY`: DashScope ASR、翻译、总结和分析使用的 key。
- `DASHSCOPE_MODEL`: 总结和分析使用的 chat model。
- `DASHSCOPE_TRANSLATION_MODEL`: 翻译模型。
- `DASHSCOPE_ASR_MODEL`: 实时 ASR 模型，通常为 `paraformer-realtime-v1`。
- `DASHSCOPE_ASR_WS_URL`: DashScope ASR WebSocket endpoint。
- `DASHSCOPE_WORKSPACE_ID`: 可选 DashScope workspace。
- `VOLCENGINE_ASR_APP_KEY`: 火山语音 app key。
- `VOLCENGINE_ASR_ACCESS_KEY`: 火山语音 access key。
- `VOLCENGINE_ASR_RESOURCE_ID`: 火山语音 resource ID。
- `VOLCENGINE_ASR_WS_URL`: 火山流式 endpoint。
- `VOLCENGINE_ASR_NOSTREAM_WS_URL`: 火山上传转写 endpoint。
- `VOLCENGINE_ASR_SSD_VERSION`: 火山 speaker clustering SSD version。

## Frontend Variables

放在 `frontend/.env.local`：

```env
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
```

不要把后端 secret 放进前端环境变量文件。

## Windows Backend Commands

后端 Python 命令必须使用仓库虚拟环境：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
