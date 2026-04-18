# Sentiment Analysis Test Script

这份稿子用于测试 `Meeting Sentiment and Engagement Analysis`，目标是让系统在一次录音中尽量同时识别出：

- `agreement`
- `disagreement`
- `tension`
- `hesitation`

建议：

- 用正常语速朗读
- 每句话之间停顿 1 秒左右
- 全程约 30 到 40 秒

## 测试口播稿

```text
我同意这个方案，整体方向是对的，我们可以继续推进。

但是我不认为现在就直接上线是可行的，当前风险还是太高了。

如果本周内数据接口还不稳定，这样做很可能会出问题，我对此比较担心。

我现在还不太确定预算能不能覆盖全部需求，也许我们需要再确认一下时间安排和资源投入。

如果这些问题能在下周前确认清楚，我会支持进入下一阶段。
```

## 预期命中信号

### 1. Agreement

建议命中句子：

```text
我同意这个方案，整体方向是对的，我们可以继续推进。
```

### 2. Disagreement

建议命中句子：

```text
但是我不认为现在就直接上线是可行的，当前风险还是太高了。
```

### 3. Tension

建议命中句子：

```text
如果本周内数据接口还不稳定，这样做很可能会出问题，我对此比较担心。
```

### 4. Hesitation

建议命中句子：

```text
我现在还不太确定预算能不能覆盖全部需求，也许我们需要再确认一下时间安排和资源投入。
```

## 预期整体结果

如果分析功能工作正常，通常应该看到：

- `overall_sentiment`: `mixed`
- `engagement_level`: `medium` 或 `high`
- `signal_counts` 中至少包含：
  - `agreement >= 1`
  - `disagreement >= 1`
  - `tension >= 1`
  - `hesitation >= 1`

## 手动检查点

测试结束后重点看：

1. 左侧 `Meeting Analysis` 面板是否出现整体分析
2. `signal_counts` 是否不是全 0
3. 右侧 transcript 中是否有高亮片段
4. 高亮标签是否和原句语义基本一致

## 如果想做更短版本

下面这版更短，约 15 到 20 秒：

```text
我同意这个方案，可以继续推进。

但我不认为现在上线是可行的，风险太高了。

我不太确定预算是否足够，也许需要再确认一下。
```
