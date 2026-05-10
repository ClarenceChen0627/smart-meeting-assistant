# 质量评估

Language:
- English: [../quality-evaluation.md](../quality-evaluation.md)
- 简体中文: `quality-evaluation.md`

上传质量评估工具用于对真实 provider 的输出做可重复的本地检查。它默认只在本地使用：真实音频、私有 manifest 和生成报告都应放在已被 Git 忽略的 `data/evals/` 下。

## 检查内容

评估工具覆盖上传会议流程。每个 manifest case 可以检查：

- 上传是否完成，以及是否发生了非预期 provider fallback
- 同一段音频在多个 provider 上的质量 / 成本对比
- transcript 数量，以及必含 / 禁用术语
- speaker 数量和最终 speaker label
- 目标语言翻译字段
- summary、action items 和 analysis 是否有基本内容
- 可选的人审参考 transcript，并计算 WER / CER 阈值
- 耗时、音频时长和本地配置的 ASR 成本估算

生成的 Markdown 报告包含 provider 对比表和人工复核区域，用于记录 speaker 是否合理、summary 是否有用等不适合完全自动打分的质量判断。

## 准备私有数据

1. 复制示例 manifest：

   ```powershell
   New-Item -ItemType Directory -Force data\evals\audio
   Copy-Item docs\examples\upload-quality.manifest.example.json data\evals\upload-quality.local.json
   ```

2. 把私有音频放到 `data/evals/audio/`。
3. 编辑 `data/evals/upload-quality.local.json`，让每个 `audio_path` 都相对 manifest 文件。
4. 补充真实术语表、期望术语、speaker 期望和可选的人审参考 transcript。

不要提交私有音频、本地 manifest 或生成报告。

## 运行评估

先用真实 provider 凭据启动后端，并隔离历史数据库：

```powershell
$env:MEETING_HISTORY_DB_PATH='..\data\evals\meeting_history.sqlite3'
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

另开一个终端运行：

```powershell
cd backend
.\.venv\Scripts\python.exe tools\evaluate_upload_quality.py --manifest ..\data\evals\upload-quality.local.json --api-base-url http://localhost:8080 --output-dir ..\data\evals\reports
```

评估工具会生成一个带时间戳的报告目录：

- `report.json`：结构化检查结果，便于自动汇总和对比。
- `report.md`：便于人工复核的摘要和记录区。
- `cases/*.meeting.json`：每个 case 的原始 `MeetingRecord` API 响应，便于排查。

## Manifest 字段

- `id`：稳定的 case 标识。
- `audio_path`：私有音频路径，可以是绝对路径，也可以相对 manifest 文件。
- `scene`：会议场景，例如 `general`、`finance` 或 `hr`。
- `provider`：期望的 ASR provider，例如 `volcengine` 或 `dashscope`。
- `providers`：可选 provider 矩阵。配置后，同一个 case 会按 provider 各跑一次，并优先于 `provider`。
- `target_lang`：可选翻译目标语言。
- `glossary_terms`：字符串或字符串数组；支持 `term=>replacement`。
- `audio_duration_seconds`：可选音频时长覆盖值，适合非 WAV 文件或只评估裁剪片段；WAV 文件会尽量自动读取时长。
- `allow_provider_fallback`：默认 `false`，避免真实 provider 评估意外落到 demo。
- `expected`：自动检查项，包括 transcript 数量、术语、speaker、翻译、summary、action items、analysis，以及可选 WER / CER 阈值。

顶层 `cost_profiles` 可用于 ASR 成本估算：

```json
{
  "cost_profiles": {
    "volcengine": {
      "currency": "CNY",
      "asr_per_audio_minute": 0.12
    }
  }
}
```

评估工具不会在代码里硬编码 provider 价格。请把费率保存在本地 manifest，并按你自己的账单假设维护。成本只用于横向比较，不承诺和供应商账单完全一致。

评估工具不负责启动 FastAPI，也默认不进入 CI。
