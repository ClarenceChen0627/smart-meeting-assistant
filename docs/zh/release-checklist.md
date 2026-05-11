# 发布检查清单

Language:
- English: [../release-checklist.md](../release-checklist.md)
- 简体中文: `release-checklist.md`

在打 tag 或分享自部署版本前使用这份检查清单。

## 配置

- `.env.example` 包含所有必需的后端变量。
- `frontend/.env.example` 只包含公开的前端 URL 覆盖配置。
- `API_ACCESS_TOKEN` 和 `CORS_ALLOW_ORIGINS` 已在生产配置文档中说明。
- `backend/tools/check_config.py` 运行时没有非预期的 `ERROR` 项。

## 验证

- 后端测试通过：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

- 前端测试和构建通过：

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
```

- Demo mode smoke flow 覆盖 live meeting、upload meeting、saved history detail 和 Markdown export。

## 文档

- `README.md` 指向 configuration、deployment、API 和 smoke testing 文档。
- 当前限制保持准确：token auth 是基础自部署保护，没有账号系统，Word/PDF export 不属于本次发布。
- 只有可见工作流变化时才刷新 screenshots。
