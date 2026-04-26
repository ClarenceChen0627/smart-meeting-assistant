# Smart Meeting Assistant 需求对比

基准文档：[`docs/Project - Smart Meeting Assistant.md`](Project%20-%20Smart%20Meeting%20Assistant.md)

更新时间：`2026-04-26`

评估范围：当前仓库中的 `frontend`、`backend`、API、持久化、测试与 README 文档。

## 总体结论

对照基准文档提出的五项核心要求，当前项目已经全部具备可演示、可运行、可持久化的实现：

| 基准要求 | 当前实现 | 结论 |
| --- | --- | --- |
| Real-time Speech-to-Text Transcription | 支持浏览器麦克风实时采集、WebSocket 音频流、Volcengine/DashScope ASR provider、实时 transcript、speaker 更新与 finalize 后 diarization | 已完成 |
| Automatic Meeting Summarization | finalize 或上传处理完成后生成结构化 summary，包含 title、overview、key topics、decisions、risks、action items，并支持用户编辑 | 已完成 |
| Machine Translation for Multilingual Meetings | 支持实时 transcript 翻译，当前单次会议选择一个目标语言，覆盖 10 种目标语言 | 已完成 |
| Context-Aware Action Item Extraction | 支持结构化 action items，包含 task、assignee、deadline、status、source excerpt、transcript index，并支持编辑和完成状态持久化 | 已完成 |
| Meeting Sentiment and Engagement Analysis | 支持会议级 sentiment / engagement analysis、agreement/disagreement/tension/hesitation 信号统计和 transcript highlight | 已完成 |

项目已经从“基础原型”推进到“带历史记录、上传处理、用户可修正输出的会议助手原型”。当前主要剩余工作不再是覆盖基准能力，而是工程化、产品化和准确率优化。

## 逐项对比

### 1. Real-time Speech-to-Text Transcription

基准要求：实时把会议语音转成文本，并支持多说话人区分。

当前实现：

- 前端通过 Web Audio API 捕获麦克风音频，并通过 WebSocket 发送给后端。
- 后端支持 `volcengine` 和 `dashscope` 两个 ASR provider，默认使用 Volcengine。
- 前端实时展示 `transcript` 和 `transcript_update`。
- Volcengine 路径支持实时 speaker clustering；DashScope fallback 可在 `finalize` 后通过离线 diarization 回填 speaker。
- `speaker_update` 会在 finalize 后同步到前端和历史记录。

结论：满足基准要求。实时 speaker 体验依赖所选 ASR provider，离线 diarization 仍是重要兜底。

### 2. Automatic Meeting Summarization

基准要求：提炼关键讨论点、决策和后续行动，输出简洁会议总结。

当前实现：

- 实时会议在 `finalize` 后生成最终 summary。
- 上传会议在后台处理完成后生成 summary。
- Summary 结构包含 `title`、`overview`、`key_topics`、`decisions`、`action_items`、`risks`。
- Summary 会持久化到 SQLite 历史记录。
- 用户可以在 Summary 面板结构化编辑 overview、topics、decisions、risks 和 action item 详情。
- 会议标题可由模型生成，并可由用户手动重命名；手动标题不会被后续 summary 覆盖。

结论：满足并超过基准要求。相比基准，当前系统还支持用户修正模型输出和持久化编辑结果。

### 3. Machine Translation for Multilingual Meetings

基准要求：支持多语言会议中的实时翻译，并尽量保留上下文和含义。

当前实现：

- 每条最终 transcript 可进入翻译流程。
- 用户可选择一个目标语言。
- 当前支持目标语言：`en`、`es`、`fr`、`de`、`zh`、`ja`、`ko`、`pt`、`ar`、`hi`。
- 翻译结果会显示在 transcript 卡片中，并保存到历史记录。
- 上传会议同样支持 transcript 翻译，结果逐步填充到历史详情。

结论：满足基准要求。当前限制是单次会议只选择一个目标语言，不是多路并行翻译。

### 4. Context-Aware Action Item Extraction

基准要求：识别类似 “I will send the report by Friday” 的承诺，并自动分配给相关参与者。

当前实现：

- Summary 生成结构化 `action_items`。
- 每条 action item 包含 task、assignee、deadline、status、source_excerpt、transcript_index、confidence、owner/deadline 显式性标记。
- 后端结合模型输出和规则补全，提高漏提取时的可用性。
- Action Items 面板支持 pending/completed 状态切换，并写回历史记录。
- Summary 编辑模式支持新增、删除、修改 action item 内容。

结论：满足并超过基准要求。当前系统不仅提取 action items，还支持用户后续维护和状态跟踪。

### 5. Meeting Sentiment and Engagement Analysis

基准要求：分析会议的情绪动态和参与模式，捕捉 agreement、disagreement、tension、hesitation 等整体互动信号。

当前实现：

- 会议过程中异步生成 analysis 快照，不阻塞 transcript 热路径。
- finalize 或上传处理完成后保存最终 analysis。
- 输出包含 `overall_sentiment`、`engagement_level`、`engagement_summary`、`signal_counts` 和 `highlights`。
- 前端 Analysis 面板展示整体情绪、参与度、趋势、信号统计和高亮片段。
- analysis 随会议记录持久化，可在历史会议中查看。

结论：满足基准要求。当前分析是会议级，不是参与者级。

## 超出基准的新增能力

- SQLite 会议历史：保存 live/upload 会议的 transcript、translation、summary、action items 和 analysis。
- 历史会议抽屉：支持打开、查看、删除历史会议。
- 上传会议模式：支持上传会议音频文件，异步转写、翻译、分析、总结，并复用实时会议结果页面。
- 可编辑历史内容：支持会议标题重命名、Summary 结构化编辑、Action Items 状态和内容维护。
- Electron 桌面壳：前端可作为 Windows-first Electron 客户端运行，但后端仍需单独启动。

## 当前限制

- Summary 仍只在 finalize 或上传处理结束后生成，不在会议过程中持续生成。
- 翻译当前是单目标语言，不支持一次会议同时输出多种目标语言。
- 原始音频文件不进入会议历史持久化。
- 上传处理是进程内异步任务，尚未引入独立任务队列。
- Sentiment / engagement analysis 是会议级，不是参与者级。
- ASR、summary、analysis 仍可能受模型识别错误、术语识别和中英混说影响。

## 最终判断

截至 `2026-04-26`，当前项目已经覆盖基准文档中的五项核心能力，并在历史管理、上传音频处理和用户可编辑输出方面明显扩展了产品形态。

后续重点建议放在：

1. 提升真实会议场景下的 ASR 和术语识别稳定性。
2. 引入更可靠的上传任务队列、任务恢复和进度管理。
3. 增强多语言场景，例如多目标语言并行输出。
4. 增加参与者级 engagement / sentiment 分析。
5. 为用户编辑内容增加审计历史或版本恢复能力。
