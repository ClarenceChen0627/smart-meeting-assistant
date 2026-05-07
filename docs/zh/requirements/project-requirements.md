# Project - Smart Meeting Assistant

Language:
- English: [../../requirements/project-requirements.md](../../requirements/project-requirements.md)
- 简体中文: `project-requirements.md`

在这个项目中，你需要设计一个智能会议助手，通过为参会者提供实时支持来增强线上和线下会议体验。系统应帮助用户转写对话、总结讨论、提取关键行动项，并提供相关洞察。

你的智能会议助手应包含以下关键功能：

## 1. 实时语音转文字

实现语音识别，把会议中的口语对话准确转写成文本。系统应支持多说话人，并能区分不同说话人，以提升会议记录清晰度。

## 2. 自动会议总结

开发智能总结模块，从对话中提取最重要的内容。总结应简洁，并提供关键议题、已做决策和后续行动的概览。

## 3. 多语言会议机器翻译

实现翻译模块，允许把会议讨论实时翻译成多种语言。该功能应帮助多语言团队顺畅沟通，在保留上下文和语义的同时翻译语音或文本讨论内容。

## 4. 上下文感知行动项提取

让系统能够从讨论中识别并跟踪行动项。助手应能识别类似 “I will send the report by Friday” 的承诺，并自动把任务分配给相关参与者。

## 5. 会议情绪与参与度分析

开发一个分析会议情绪动态和参与模式的模块。系统不应只关注个人承诺，还应捕捉更广泛的互动信号，例如同意、反对、紧张或犹豫（例如 “I am not convinced this will work”）。

助手应提供整体情绪概览，并高亮讨论中情绪上重要的时刻。

该项目要求你应用 NLP、语音处理和上下文理解能力，创造一个有助于提升职场生产力的 AI 工具。鼓励你设计数据集，并探索创新功能来增强系统效果。

## Reference

1. Tan, Haochen, et al. “Reconstruct Before Summarize: An Efficient Two-Step Framework for Condensing and Summarizing Meeting Transcripts.” *Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing*. 2023.
2. Wu, Han, et al. “VCSUM: A Versatile Chinese Meeting Summarization Dataset.” *Findings of the Association for Computational Linguistics: ACL 2023*.
3. H. Zhang, P. S. Yu, and J. Zhang, “A systematic survey of text summarization: From statistical methods to large language models”, *arXiv preprint* arXiv:2406.11289, 2024.
4. Park, Chanjun, et al. “BTS: Back TranScription for speech-to-text post-processor using text-to-speech-to-text.” *Proceedings of the 8th Workshop on Asian Translation (WAT2021)*. 2021.
