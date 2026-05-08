# Smart Meeting Assistant

Language:
- English: [README.md](README.md)
- 简体中文: `README-zh.md`

Smart Meeting Assistant 是一个基于 React 18 + FastAPI 的会议助手，支持实时转写、转写翻译、会议总结、行动项提取、情绪 / 参与度分析、上传会议处理和历史会议保存。前端可以运行在浏览器中，也可以通过 Windows-first Electron 桌面壳运行。

## 快速开始

### 1. 无外部 AI key 运行

Demo 模式是最快的本地验证方式。它使用确定性的 mock ASR、翻译、总结和分析结果，不调用外部模型。

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

编辑 `.env`：

```env
DEMO_MODE=1
DEFAULT_ASR_PROVIDER=demo
DIARIZATION_MODE=disabled
```

启动后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

```bash
cd backend
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

打开：

- 前端：`http://localhost:5173`
- 后端健康检查：`http://localhost:8080/api/health`

### 2. 使用真实服务商运行

复制 `.env.example` 到 `.env`，填入服务商凭据，然后选择：

- `DEFAULT_ASR_PROVIDER=volcengine`：使用火山 Doubao ASR。
- `DEFAULT_ASR_PROVIDER=dashscope`：使用 DashScope Paraformer 实时 ASR。

最小配置矩阵和 diarization 前置条件见 [Configuration](docs/configuration.md)。

## 功能

- 浏览器麦克风采集，通过 WebSocket 实时传音频。
- 可切换 ASR provider：Volcengine Doubao、DashScope Paraformer、本地 demo。
- 实时 transcript 展示与 speaker label。
- transcript 翻译，支持 10 种目标语言。
- finalize 后生成会议标题、概览、议题、决策、风险和行动项。
- 会议情绪 / 参与度的增量分析和最终分析，并提供参与者级汇总。
- 上传会议模式，支持后台 worker 处理和前端轮询渐进展示。
- SQLite 历史会议保存，覆盖 live 和 upload 两类来源。
- 上传会议可选择保留原始音频，并在历史记录中保存音频元数据。
- live 和 upload 均支持持久化自定义术语表，用于术语纠错和总结 / 分析提示。
- 已保存会议可改标题、speaker label、总结字段和行动项状态。
- 可选 Windows portable Electron 桌面客户端。

## 项目结构

```text
smart-meeting-assistant/
├─ frontend/              React + Vite UI 和 Electron shell
├─ backend/               FastAPI 后端
├─ backend/tests/         pytest 后端测试
├─ data/                  本地运行数据
├─ docs/                  架构、API、配置文档
├─ .env.example           后端环境变量模板
├─ docker-compose.yml
├─ README.md
└─ README-zh.md
```

## 常用命令

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

前端：

```powershell
cd frontend
npm install
npm run test
npm run build
npm run dev
```

```bash
cd frontend
npm install
npm run test
npm run build
npm run dev
```

Electron：

```powershell
cd frontend
npm run dev:electron
npm run electron:pack
```

```bash
cd frontend
npm run dev:electron
npm run electron:pack
```

Docker：

```powershell
docker-compose up --build
```

```bash
docker-compose up --build
```

## 文档

- [Architecture](docs/architecture.md)：系统总览、实时流程、上传流程和会议状态图。
- [Configuration](docs/configuration.md)：demo 模式、provider 变量、前端覆盖配置和最小配置矩阵。
- [质量评估](docs/zh/quality-evaluation.md)：使用私有音频 manifest 和复核报告，在本地评估真实 provider 的上传会议质量。
- [API Reference](docs/api.md)：HTTP 接口、WebSocket 消息和 meeting record 字段。
- [Speaker Diarization](docs/diarization.md)：offline / hybrid diarization 配置。
- [diart Setup](docs/diart.md)：Windows 下实时 diart speaker update 的详细启动说明（[中文](docs/zh/diart.md)）。
- [Requirements](docs/requirements/project-requirements.md)：原始项目需求和实现对比资料（[comparison](docs/requirements/requirements-comparison.md)，[中文](docs/zh/requirements/project-requirements.md)，[中文对比](docs/zh/requirements/requirements-comparison.md)）。
- [Technical Implementation](docs/technical-implementation.md)：英文技术实现说明。
- [中文技术实现](docs/zh/technical-implementation.md)：中文技术实现说明。

## 演示截图

- [实时 demo 工作区](docs/assets/screenshots/demo-live.png)
- [上传会议完成态](docs/assets/screenshots/demo-upload-ready.png)
- [历史会议详情](docs/assets/screenshots/demo-history-detail.png)

## 当前限制

- Hybrid 实时 diarization 的 speaker label 是临时结果，finalize 后的 pyannote 结果才是最终准结果。
- Volcengine 原生 speaker clustering 只作用于 Volcengine ASR provider 路径。
- Summary 只在 `finalize` 后生成，不在会议中持续刷新。
- 实时 ASR 在术语表纠错前仍可能误识别技术术语。
- 移动端浏览器录音可靠性弱于桌面端。
- Upload processing 使用进程内 worker queue；分布式 worker queue 仍不在当前范围内。

## Roadmap

- 短期：真实会议上传质量评估包已建立，支持私有音频 manifest、本地 provider 运行、自动检查和人工复核报告。
- 中期：提升真实会议准确率和可修正性，包括持久化术语表、speaker 重命名 / 合并、移动端录音稳定性和会中滚动摘要。
- 长期：面向生产使用补强质量治理和运行可靠性，包括 provider 质量 / 成本评估、分布式上传队列、任务恢复、可观测性和编辑审计历史。

## License

MIT
