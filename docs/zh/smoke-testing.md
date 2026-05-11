# Smoke Testing

Language:
- English: [../smoke-testing.md](../smoke-testing.md)
- 简体中文: `smoke-testing.md`

使用 demo mode 可以在没有外部 AI provider key 的情况下快速验证本地流程。

## 后端

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```env
DEMO_MODE=1
DEFAULT_ASR_PROVIDER=demo
DIARIZATION_MODE=disabled
```

运行检查：

```powershell
cd backend
.\.venv\Scripts\python.exe tools\check_config.py
.\.venv\Scripts\python.exe -m pytest -m smoke
```

## 前端

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
```

## 手动流程

1. 只有需要人工验收时才启动后端和前端。
2. 打开前端，确认 `/api/health` 可访问。
3. 启动一个 demo live meeting，停止后确认 transcript、summary、action items 和 history save。
4. 在 demo mode 上传一个小音频文件，确认轮询最终到达 `finalized`。
5. 打开 Meeting History，搜索/筛选记录，切换 favorite/archive，并编辑 tags。
6. 导出 standard notes、Chinese minutes 和 action items Markdown。
7. 设置 `API_ACCESS_TOKEN`，重启后端，确认未鉴权的受保护请求失败；在 UI 中输入 token 后，确认同一流程恢复可用。
