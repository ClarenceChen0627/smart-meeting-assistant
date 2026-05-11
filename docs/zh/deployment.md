# 部署

Language:
- English: [../deployment.md](../deployment.md)
- 简体中文: `deployment.md`

Smart Meeting Assistant 面向私有自部署。生产部署时，FastAPI 后端应放在 HTTPS 反向代理后面，React 前端应从同一个 HTTPS origin 提供，或从显式允许的 origin 提供。

## 推荐生产形态

- 后端：FastAPI 监听 `127.0.0.1:8080`，或运行在 Docker 内部网络。
- 前端：通过 Web server 提供 Vite 静态构建产物，或使用现有 frontend container。
- 反向代理：终止 HTTPS，并把 HTTP API 流量和 `/ws/meeting` WebSocket upgrade 转发到后端。
- 存储：为 `MEETING_HISTORY_DB_PATH`、`UPLOAD_QUEUE_DIR` 和可选 `RAW_AUDIO_DIR` 配置持久卷。

## 必要安全配置

在把应用暴露到可信开发机之外前，先设置：

```env
API_ACCESS_TOKEN=replace-with-a-long-random-token
CORS_ALLOW_ORIGINS=https://meetings.example.com
MAX_UPLOAD_BYTES=524288000
ALLOWED_UPLOAD_CONTENT_TYPES=audio/wav,audio/x-wav,audio/mpeg,audio/mp3,audio/mp4,audio/webm,audio/ogg,video/webm,application/octet-stream
```

`/` 和 `/api/health` 保持公开，用于基础存活检查。设置 `API_ACCESS_TOKEN` 后，会议数据、上传、诊断、审计事件、术语表 API、转写工具接口和 `/ws/meeting` 都需要 token。

用户在前端输入 access token 后，浏览器会把它保存在 local storage。WebSocket 鉴权使用 `access_token` query 参数，因为浏览器 WebSocket API 不支持自定义请求 header。如果担心泄露 token，应配置反向代理访问日志，不保留 query string。

## 反向代理注意事项

反向代理必须转发：

- `/api/*` 到后端 HTTP 服务。
- `/ws/meeting` 到后端，并保留 WebSocket upgrade headers。
- 前端静态资源到 frontend server 或静态文件目录。

移动端麦克风采集需要 HTTPS 或其他 secure context。手机局域网测试时，应使用局域网主机名上的 HTTPS，而不是 plain HTTP。

## 配置自检

首次使用前运行只读配置自检：

```powershell
cd backend
.\.venv\Scripts\python.exe tools\check_config.py
```

```bash
cd backend
./.venv/Scripts/python.exe tools/check_config.py
```

该检查会报告缺失的 provider key 和路径状态，但不会打印密钥明文。
