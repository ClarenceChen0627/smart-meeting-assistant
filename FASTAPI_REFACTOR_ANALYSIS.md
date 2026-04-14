# Smart Meeting Assistant FastAPI 重构评估

> 说明：这是重构前后的技术评估文档，保留用于记录重构决策过程；当前实际目录结构与运行方式请以 `README.md` 为准。

## 1. 结论

可以，而且这个项目**比较适合**用 Python + FastAPI 重构核心服务层。

但需要先把“重构整个项目”这句话拆开：

- 如果你的意思是：**把当前 Java 后端 + Python 模型服务统一重构成一个 FastAPI 服务**，结论是 `可以，且值得做`。
- 如果你的意思是：**连 Vue 前端也改成 FastAPI 模板渲染项目**，结论是 `技术上能做，但不建议`。

我对这个仓库的判断是：

- 当前真实业务复杂度不高。
- 没有数据库和复杂权限体系。
- 核心能力集中在 3 件事：`WebSocket 音频流`、`ASR 转写`、`LLM 摘要生成`。
- 仓库里已经存在一个独立的 FastAPI 模型服务，说明 Python 路线本身已经被部分验证。

所以，**最合理的重构目标不是“全站改 Python 页面应用”，而是“保留 Vue 前端，把后端统一成 FastAPI”**。

## 2. 当前项目结构理解

当前仓库实际上是三段式结构：

### 2.1 前端

目录：`frontend`

技术栈：

- Vue 3
- TypeScript
- Vite
- Element Plus

职责：

- 采集浏览器麦克风音频
- 通过 WebSocket 发送音频二进制数据
- 接收后端推送的 `transcript` 和 `summary`
- 展示实时转写和会议总结

前端当前连接的是：

- `ws://<host>:8080/ws/meeting?scene=finance|hr`

也就是说，前端**直接依赖 Java 后端的 WebSocket 协议**。

### 2.2 Java 后端

目录：`backend`

技术栈：

- Java 21
- Spring Boot 3.4
- Spring WebSocket
- Spring AI Alibaba
- OkHttp

职责：

- 提供 `/api/health`
- 提供 `/ws/meeting`
- 接收前端音频块
- 调用阿里云 ASR
- 维护会话内 transcript 列表
- 每累计 10 条转写生成一次摘要
- 通过 WebSocket 把 transcript / summary 推送回前端

### 2.3 Python 模型服务

目录：`model`

技术栈：

- FastAPI
- Uvicorn
- httpx
- websockets
- pydub

职责：

- 提供 `/api/transcribe`
- 提供 `/api/transcribe/batch`
- 提供 `/ws/transcribe`
- 直接调用阿里云 ASR

但它目前有两个明显特征：

- 它**没有接入当前主链路**，因为 `docker-compose.yml` 只启动前端和 Java 后端，没有启动这个服务。
- 前端也**没有直接连接它**，前端仍然连接的是 Java 的 `/ws/meeting`。

所以从实际运行链路看：

**当前主系统是 Vue + Spring Boot。FastAPI 服务更像一个未接管主链路的实验性或预备模块。**

## 3. 为什么这个项目适合重构成 FastAPI

## 3.1 业务边界清晰

这个项目没有看到复杂的：

- 数据库模型
- 多角色权限
- 大量 REST API
- 分布式事务
- 复杂后台管理逻辑

核心是实时流处理和 AI 编排，这类问题用 Python 做并不吃亏。

## 3.2 当前后端职责本身就偏“Python 友好”

Java 后端的主要能力是：

- WebSocket 会话处理
- 调外部 ASR 接口
- 调 LLM
- 拼接 prompt
- 解析结构化结果

这些事情在 Python 里都可以自然完成，而且生态更直接：

- FastAPI 处理 HTTP / WebSocket
- `httpx` / `aiohttp` 调外部接口
- Pydantic 定义消息模型
- DashScope / OpenAI 兼容 SDK 做 LLM 调用
- asyncio 更适合做流式编排

## 3.3 仓库已经有 Python 代码基础

不是从 0 开始。现有 `model` 已经证明：

- 团队接受 Python
- 依赖链已经初步建立
- Dockerfile 和 requirements 已经具备雏形

这会降低迁移成本。

## 3.4 当前项目规模不大，重写成本可控

从仓库观察：

- Java 主代码文件数量不多
- Python 服务文件数量也不多
- 没有测试包
- 没有持久化层

这意味着这是一个**适合做服务层统一重构**的小中型项目，而不是一个需要多年包袱迁移的大系统。

## 4. 目前代码里暴露出的关键问题

这些问题不影响“能不能用 FastAPI 重构”的答案，但会影响“重构值不值得”和“该怎么重构”。

## 4.1 Python 服务并未真正接管系统

现状：

- `docker-compose.yml` 没有 `model` 服务
- 前端也没有连接 Python 服务

含义：

- 现在不是一个完整的 Python 架构
- 如果要重构，推荐把它从“旁路服务”升级为“主服务”

## 4.2 音频格式链路存在明显风险

前端通过 `MediaRecorder` 发送的是：

- `audio/webm;codecs=opus`

但无论 Java 还是 Python ASR 调用里，都把上传内容按：

- `format=wav`

来处理。

这说明当前实现里至少存在以下风险之一：

- 浏览器发来的数据并不是真正的 WAV
- 后端没有做可靠转码
- ASR 调用可能依赖“碰巧能用”的输入
- 真实环境下转写稳定性可能不高

这件事在 FastAPI 重构时必须正面解决，不能只是语言迁移。

## 4.3 ASR 鉴权实现看起来是占位版本

Java 和 Python 里都出现了类似逻辑：

- `X-NLS-Token` 直接使用 `AccessKeyId`

代码注释也写了应该用真正的临时 token / STS。

这说明当前阿里云 ASR 接入大概率还是简化版实现。  
如果要做正式重构，建议同时把鉴权链路补正。

## 4.4 说话人识别并不是真正的 diarization

当前 `speaker` 分配逻辑本质上是：

- 根据时间段或索引交替给 `Speaker_A / Speaker_B`

这不是实际的说话人分离，只是占位策略。

所以如果你后续对“会议助手”效果有更高要求，FastAPI 重构不应只是搬代码，而应顺手把这一层能力边界写清楚：

- 继续保留“伪 speaker 标记”
- 或切换到真正支持 diarization 的服务/模型

## 4.5 Java WebSocket 并发模型比较粗糙

`MeetingWebSocketHandler` 对每一段音频直接 `new Thread()` 处理。

这在低并发 demo 中能跑，但存在几个问题：

- 每个音频块起一个线程，资源模型不可控
- 没有统一线程池
- 会话内音频片段顺序与处理完成顺序可能不稳定
- 总结生成时机与会话关闭时机容易错位

FastAPI 重构时可以直接把这部分改成：

- asyncio 任务模型
- 每会话队列
- 后台消费者

这样会更稳。

## 4.6 “连接关闭后再发总结”这条链路有逻辑缺陷

Java 后端在 `afterConnectionClosed` 里会尝试生成 summary。  
但连接已经关闭后，再向前端发送消息通常没有意义。

这意味着：

- 用户停止录音后，最终总结不一定能可靠送达
- 当前前端能否稳定看到最后摘要，取决于关闭前是否刚好触发过“每 10 条生成一次”

这个问题和语言无关，但非常适合在重构时修正。

## 5. 能否用 FastAPI 完整承接当前后端能力

答案是：**可以。**

以下能力都可以在 FastAPI 中直接承接：

### 5.1 WebSocket 会议通道

Java 当前的 `/ws/meeting` 可以迁移为 FastAPI WebSocket：

- 接收前端音频块
- 基于 query 参数识别 `scene`
- 缓存当前 session transcript
- 推送 `transcript`
- 推送 `summary`

这部分 FastAPI 完全胜任。

### 5.2 健康检查与普通 HTTP API

`/api/health`、转写接口、批量接口都适合迁移到 FastAPI。

### 5.3 ASR 集成

当前 Python 服务已经有阿里云 ASR 调用雏形，所以迁移不是从 0 开始。

建议做法：

- 把 `model` 的 ASR 逻辑合并到新的 FastAPI 主服务
- 同时补上音频格式标准化
- 同时补上正确 token 鉴权

### 5.4 LLM 摘要生成

Java 现在用的是 Spring AI Alibaba。  
这一层迁移到 Python 并不困难，甚至通常更自由。

可选方式：

- 直接调用 DashScope API
- 使用兼容 SDK
- 强制要求模型返回 JSON，避免现在这种靠文本标题切分的脆弱解析

### 5.5 Docker 化与部署

当前部署已经是容器化思路。  
把 `backend + model` 合并成一个 `fastapi-backend` 容器，部署上反而更简单。

## 6. 哪些部分不建议“用 FastAPI 重构”

## 6.1 不建议把 Vue 前端改成 FastAPI 模板项目

原因很简单：

- 当前前端已经完成基本交互
- 音频采集、实时列表、状态展示这些更适合前端框架做
- 改成 Jinja2 模板不会带来明显收益
- 反而会损失前端交互开发效率

所以更合理的定义是：

- 前端继续保留 Vue
- 后端统一成 FastAPI

如果你非要“整个仓库都 Python 化”，技术上可以把前端构建产物交给 FastAPI 静态托管，但**不建议把前端逻辑本身改写成服务器模板页面**。

## 7. 推荐的目标架构

建议重构后的结构如下：

```text
smart-meeting-assistant/
├─ frontend/                     # 保留 Vue 3
├─ backend-fastapi/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ api/
│  │  │  ├─ health.py
│  │  │  ├─ transcribe.py
│  │  │  └─ websocket.py
│  │  ├─ services/
│  │  │  ├─ asr_service.py
│  │  │  ├─ summary_service.py
│  │  │  ├─ audio_codec_service.py
│  │  │  └─ session_manager.py
│  │  ├─ schemas/
│  │  │  ├─ transcript.py
│  │  │  ├─ summary.py
│  │  │  └─ ws_message.py
│  │  ├─ core/
│  │  │  ├─ config.py
│  │  │  └─ logging.py
│  │  └─ clients/
│  │     ├─ aliyun_asr_client.py
│  │     └─ dashscope_client.py
│  ├─ tests/
│  ├─ requirements.txt
│  └─ Dockerfile
└─ docker-compose.yml
```

核心原则：

- 一个 FastAPI 服务承接当前 Java 后端与 Python 模型服务
- 前端协议尽量保持不变，减少联调成本
- WebSocket 消息格式兼容现有前端 `transcript | summary`

## 8. 推荐的重构策略

不建议一把梭“推倒重写”，建议按下面顺序做。

## 8.1 第一阶段：先做兼容式 FastAPI 骨架

目标：

- 建立新的 FastAPI 服务
- 先实现 `/api/health`
- 实现与当前前端兼容的 `/ws/meeting`
- 保持消息格式不变

这样可以先证明：

- 前端不用大改
- FastAPI 可以接住主链路

## 8.2 第二阶段：迁移摘要服务

先迁移 LLM 摘要，而不是一开始就重做全部 ASR。

原因：

- 这部分逻辑更确定
- 输入输出更容易验证
- 可以尽快摆脱 Spring AI 依赖

同时建议把输出改为：

- 模型直接返回 JSON
- Pydantic 校验

不要再依赖文本分段解析。

## 8.3 第三阶段：迁移 ASR 与音频标准化

这是最关键阶段。

要解决：

- 浏览器 `webm/opus` 到 ASR 可接受格式的转换
- 鉴权
- 超时控制
- 异常重试
- mock fallback 是否保留

如果这一层不做好，换什么框架都只是表面重构。

## 8.4 第四阶段：替换 docker-compose 主链路

完成后：

- 下掉 Java 后端容器
- 把 Python 服务升级为唯一主服务
- 前端连接改到 FastAPI 服务

## 8.5 第五阶段：补测试

当前仓库几乎没有测试。  
重构完成后至少应补这几类：

- WebSocket 协议测试
- summary 结构化输出测试
- ASR client 单测
- 音频格式转换测试
- 关键流程集成测试

## 9. 风险评估

## 9.1 低风险项

- 健康检查 API 迁移
- 配置迁移
- Docker 化
- 摘要 prompt 迁移
- WebSocket 消息结构迁移

## 9.2 中风险项

- 会话状态管理
- 异步任务调度
- LLM 输出结构化约束
- 与前端实时交互的一致性

## 9.3 高风险项

- 浏览器音频编码与 ASR 接口格式匹配
- 阿里云 ASR 鉴权与稳定性
- 真正的说话人识别需求
- 高并发下的 WebSocket 音频流处理

所以要明确：

**FastAPI 重构最大的风险不是框架本身，而是音频链路和第三方 ASR 集成质量。**

## 10. 是否值得做

我的判断是：**值得，但要按“后端统一重构”来做，不要按“全栈全部推翻”来做。**

适合做的原因：

- 当前系统规模小，迁移成本可控
- 仓库已经有 Python 服务原型
- Java 后端没有很重的领域沉淀
- Python 更适合后续扩展 AI / 音频 / prompt / 模型编排
- 可以把现在分裂的 Java + Python 合并为一个更统一的服务层

不适合做“大而全重写”的地方：

- 前端没有必要重写成 Python 模板
- 如果你现在最关心的是“尽快上线可用版本”，那应该先修复音频与鉴权问题，再决定是否整体迁移

## 11. 最终建议

建议采用下面这个决策：

### 推荐结论

**可以用 FastAPI 重构，而且建议重构的范围是：**

- 保留 `frontend`
- 替换 `backend`
- 吸收 `model`
- 最终形成 `Vue + FastAPI` 两层结构

### 不推荐结论

**不建议把“整个项目”理解成“前端也改成 FastAPI 模板页面”。**

### 建议的项目目标

把现在的：

- `Vue + Spring Boot + 独立 FastAPI`

收敛为：

- `Vue + FastAPI`

### 工期粗估

如果目标是“功能对齐 + 顺手修复关键实现缺陷”，我给出的粗估是：

- 最小可运行版本：`3 到 5 个工作日`
- 可稳定联调版本：`5 到 8 个工作日`
- 如果要顺带补测试、修正音频链路、提升可靠性：`8 到 12 个工作日`

## 12. 一句话判断

**能重构，且建议重构；但应重构的是服务层，不是把前端也改写成 FastAPI 页面项目。**
