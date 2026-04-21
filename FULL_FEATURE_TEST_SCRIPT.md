# Full Feature Test Script

这份口播稿用于一次性验证当前桌面端的全部核心能力：

- `Live Transcript`
- `Translation`
- `Meeting Summary`
  - `To-Dos`
  - `Decisions`
  - `Risks`
- `Meeting Analysis`
  - `agreement`
  - `disagreement`
  - `tension`
  - `hesitation`

建议：

- 用正常语速朗读
- 每句话之间停顿 0.5 到 1 秒
- 完整时长约 45 到 60 秒

## 测试口播稿

```text
大家好，我先同步一下当前项目的整体情况。我同意继续推进这个方案，整体方向是对的，而且如果按计划执行，我们下周可以进入下一阶段。

但是我不认为现在就直接上线是可行的，当前风险还是太高了。如果本周内数据接口还不稳定，这样做很可能会出问题，我对此比较担心。

我现在还不太确定预算能不能覆盖全部需求，也许我们需要再确认一下时间安排和资源投入。

接下来有几个明确事项：第一，我会在这周五之前整理并提交最新的项目作品集。第二，请产品和后端同学在下周一之前确认接口稳定性和上线范围。

我们今天先决定，不在本周上线，等接口和预算确认完成后，再安排下一轮评审。如果这些问题能在下周前确认清楚，我会支持进入下一阶段。
```

## 预期 Summary 结果

### To-Dos

理论上应该至少出现类似内容：

- `这周五之前整理并提交最新的项目作品集`
- `下周一之前确认接口稳定性和上线范围`

### Decisions

理论上应该至少出现类似内容：

- `今天决定本周不上线`
- `等接口和预算确认完成后再安排下一轮评审`
- `如果问题确认清楚，下周进入下一阶段`

### Risks

理论上应该至少出现类似内容：

- `数据接口还不稳定`
- `当前上线风险较高`
- `预算是否覆盖全部需求仍待确认`

## 预期 Analysis 结果

### Agreement

建议命中句子：

```text
我同意继续推进这个方案，整体方向是对的。
```

### Disagreement

建议命中句子：

```text
但是我不认为现在就直接上线是可行的。
```

### Tension

建议命中句子：

```text
当前风险还是太高了。
如果本周内数据接口还不稳定，这样做很可能会出问题，我对此比较担心。
```

### Hesitation

建议命中句子：

```text
我现在还不太确定预算能不能覆盖全部需求，也许我们需要再确认一下时间安排和资源投入。
```

## 预期整体表现

### Live Transcript

- 在默认的 `Transcript` 选项卡中，发言内容应持续更新
- 页面支持向下滚动查看会议记录

### Translation

- 每条 transcript 内容气泡下方应显示目标语言译文

### Meeting Summary

- 切换到 `Action Items` 选项卡，应分类显示 `To-Dos / Decisions / Risks` 列表（可手动勾选状态）
- 切换到 `Summary` 选项卡可以查看结构化大纲
- 如果模型提取不完全，也不应该完全没有 summary

### Meeting Analysis

- 切换到 `Analysis` 选项卡，应能看到监控表盘：
  - `Overall Sentiment`
  - `Engagement Level`
  - `Engagement Summary`
  - `Signal Distribution` (互动信号的数据饼图)
- 下方应展示 `Emotionally Significant Moments`，直接列出关键高亮片段，并包含 AI 原因分析

## 快速检查清单

录音结束后你可以按这个顺序看：

1. `Transcript` 选项卡：是否完整显示，能否滚动到底部
2. `Transcript` 选项卡：翻译是否逐条挂载出现
3. `Action Items` 选项卡：是否有抽取的 `To-Dos / Decisions / Risks`
4. `Analysis` 选项卡：是否有非空的 `Signal Distribution` 饼图
5. `Analysis` 选项卡底层的高亮片段是否和口播内容大致一致，理由合理
