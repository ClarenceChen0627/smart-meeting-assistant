# diart 实时说话人分离启动说明

Language:
- English: [../diart.md](../diart.md)
- 简体中文: `diart.md`

本文档说明如何在本项目中启动 diart 实时说话人分离。当前设计是双环境、双阶段：

- 主后端运行在 `backend\.venv`，负责 FastAPI、ASR、业务逻辑，以及会议结束后的 pyannote 最终确认。
- diart worker 运行在 `backend\.venv-diart`，只负责会议进行中的实时说话人分离。
- 两个环境不共享 Python 包；主后端通过 `DIART_PYTHON_PATH` 启动子进程，并通过管道传递 PCM 音频和 JSON 结果。

## 什么时候会启动 diart

diart 是懒加载，不会在后端启动时立即下载或加载模型。只有满足以下条件，并且有会议会话开始后，主后端才会启动 diart worker：

```env
DEFAULT_ASR_PROVIDER=dashscope
DASHSCOPE_ASR_MODEL=paraformer-realtime-v1
DIARIZATION_MODE=hybrid
HF_HOME=models/huggingface
PYANNOTE_CACHE=models/huggingface/hub
HF_HUB_DISABLE_SYMLINKS=1
HF_HUB_OFFLINE=1
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
DIART_PYTHON_PATH=D:\Project\smart-meeting-assistant\backend\.venv-diart\Scripts\python.exe
```

实际流程是：

```text
会议开始
  -> 主后端 backend\.venv 接收麦克风 PCM 音频
  -> DashScope paraformer-realtime-v1 做实时 ASR
  -> 主后端按 DIART_PYTHON_PATH 启动 backend\.venv-diart 子进程
  -> diart worker 加载 pyannote/segmentation + pyannote/embedding
  -> 会议中推送 speaker_update，speaker_is_final=false
  -> 会议结束
  -> 主后端用 pyannote/speaker-diarization-community-1 做最终确认
  -> 推送最终 speaker_update，speaker_is_final=true
```

Volcengine / 豆包路径不走 diart。它使用 provider 自己返回的 speaker clustering。

## 1. 准备主后端环境

主后端所有 Python 命令必须使用 `backend\.venv\Scripts\python.exe`，不要使用系统 Python、全局 pip、全局 pytest 或全局 uvicorn。

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动主后端也必须使用主 venv：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## 2. 创建 diart 独立环境

`diart==0.9.2` 需要 `numpy<2`，而主后端的 pyannote final diarization 使用 `pyannote.audio` 4.x 和 `numpy>=2`。因此不要把 diart 装进 `backend\.venv`，要单独创建 `backend\.venv-diart`。

使用主后端 venv 创建 diart venv：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv\Scripts\python.exe -m venv .venv-diart
```

安装 diart 依赖，使用官方 PyPI 源：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv-diart\Scripts\python.exe -m pip install -i https://pypi.org/simple --upgrade pip
.\.venv-diart\Scripts\python.exe -m pip install -i https://pypi.org/simple -r requirements-diart.txt
```

安装完成后检查依赖：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv-diart\Scripts\python.exe -m pip check
```

正常结果应该是：

```text
No broken requirements found.
```

## 3. CPU 版和 GPU 版 torch

如果只用官方 PyPI 源安装 `torch==2.8.0`、`torchaudio==2.8.0`、`torchvision==0.23.0`，Windows 上通常会得到 CPU 版，例如：

```text
torch 2.8.0+cpu
torchaudio 2.8.0+cpu
torchvision 0.23.0+cpu
```

这可以正常跑通 diart，但 GPU 通常会更快。diart worker 当前会自动判断：

```text
torch.cuda.is_available() == true  -> 使用 cuda
torch.cuda.is_available() == false -> 使用 cpu
```

项目当前没有 `DIART_DEVICE` 配置项，不需要手动设置设备。

如果要使用 GPU，需要把 `.venv-diart` 里的 torch 栈换成和本机 NVIDIA 驱动匹配的 CUDA wheel。这个源不是 PyPI，而是 PyTorch 官方 CUDA wheel index。例如 CUDA 12.8：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv-diart\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cu128 torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0
```

检查 GPU 是否可用：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv-diart\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

如果输出 `True` 和显卡名称，diart worker 会自动使用 GPU。

## 4. 配置 .env

在项目根目录 `.env` 中配置以下内容：

```env
DEFAULT_ASR_PROVIDER=dashscope
DASHSCOPE_ASR_MODEL=paraformer-realtime-v1

DIARIZATION_MODE=hybrid
HUGGINGFACE_TOKEN=your-huggingface-token
HF_HOME=models/huggingface
PYANNOTE_CACHE=models/huggingface/hub
HF_HUB_DISABLE_SYMLINKS=1
HF_HUB_OFFLINE=1
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

DIARIZATION_MODEL=pyannote/speaker-diarization-community-1

REALTIME_DIARIZATION_DURATION_SECONDS=5
REALTIME_DIARIZATION_STEP_SECONDS=0.5
REALTIME_DIARIZATION_LATENCY_SECONDS=1
DIART_SEGMENTATION_MODEL=pyannote/segmentation
DIART_EMBEDDING_MODEL=pyannote/embedding
DIART_PYTHON_PATH=D:\Project\smart-meeting-assistant\backend\.venv-diart\Scripts\python.exe
```

说明：

- `DIARIZATION_MODE=disabled`：后端不做 speaker diarization，Volcengine 原生 speaker clustering 仍然可用。
- `DIARIZATION_MODE=offline`：会议结束后才用 `DIARIZATION_MODEL` 做 pyannote final diarization。
- `DIARIZATION_MODE=hybrid`：会议中用 diart 实时分离，会议结束后用 `DIARIZATION_MODEL` 最终确认。
- `DIART_SEGMENTATION_MODEL` 和 `DIART_EMBEDDING_MODEL` 是 diart 组件模型，不是最终 pyannote pipeline。
- `DIARIZATION_MODEL` 是会议结束后最终确认模型，不传给 diart。
- `HF_HOME=models/huggingface` 会把 Hugging Face 下载内容放到项目内；相对路径会按项目根目录解析。
- `PYANNOTE_CACHE=models/huggingface/hub` 会让 pyannote.audio 3.x 使用同一个项目内 Hugging Face hub cache。
- `HF_HUB_DISABLE_SYMLINKS=1` 会让 Hugging Face 复制缓存文件，避免 Windows 非管理员终端创建符号链接时报 `WinError 1314`。
- `HF_HUB_OFFLINE=1` 会直接使用本地缓存，避免 Hugging Face HEAD 重试日志；换模型或首次下载时要设回 `0` 或删除。
- `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` 会让可信的 pyannote.audio 3.x checkpoint 在 PyTorch 2.6+ 上使用兼容加载方式。

Hugging Face 账号需要接受相关模型的使用条款，至少包括：

- `pyannote/speaker-diarization-community-1`
- `pyannote/segmentation`
- `pyannote/embedding`

## 5. 模型缓存位置

默认情况下，Hugging Face 会把模型下载到用户目录下，例如 Windows 上的 `C:\Users\<用户名>\.cache\huggingface`。本项目推荐改为项目内缓存：

```env
HF_HOME=models/huggingface
```

后端启动时会把这个相对路径解析成：

```text
D:\Project\smart-meeting-assistant\models\huggingface
```

主后端 pyannote 和 diart worker 会共用这个缓存目录：

```text
backend\.venv:
  pyannote/speaker-diarization-community-1

backend\.venv-diart:
  pyannote/segmentation
  pyannote/embedding
```

`models/` 是本地运行数据，已经被 `.gitignore` 忽略，不要提交到 Git。

diart 当前依赖的 `pyannote.audio` 3.x 还有两个额外注意点：

```env
PYANNOTE_CACHE=models/huggingface/hub
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
```

`PYANNOTE_CACHE` 必须指到同一个 hub cache，否则 pyannote.audio 3.x 会默认去 `C:\Users\<用户名>\.cache\torch\pyannote` 查模型，导致已经下载到项目内的模型无法被 diart 复用。`TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` 是为了兼容 PyTorch 2.6+ 的 `weights_only=True` 默认行为；本项目加载的是明确指定的 pyannote 官方模型，属于可信 checkpoint。

Windows 默认不一定允许普通终端创建符号链接。为了避免以后下载模型时出现：

```text
OSError: [WinError 1314] 客户端没有所需的特权
```

本项目建议保留：

```env
HF_HUB_DISABLE_SYMLINKS=1
```

这样 Hugging Face 会复制文件而不是创建 symlink。缺点是缓存可能多占一些磁盘空间；如果你以后开启 Windows Developer Mode 或用管理员终端运行，也可以去掉这个变量来恢复 symlink 缓存。

### 离线缓存模式

模型已经预下载时建议开启：

```env
HF_HUB_OFFLINE=1
```

开启后，pyannote 和 diart 会直接使用 `models/huggingface` 里的项目缓存，不再对 Hugging Face 发 HEAD 请求，也就不会出现网络被拦截时的重试日志。

换模型或首次下载模型时关闭：

```env
HF_HUB_OFFLINE=0
```

也可以临时删除这一行。模型下载完成后再改回 `1`。

## 6. 启动后端

只需要启动主后端，不需要手动启动 diart：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

当用户选择 DashScope `paraformer-realtime-v1` 并开始会议后，主后端会自动启动：

```text
D:\Project\smart-meeting-assistant\backend\.venv-diart\Scripts\python.exe app/workers/diart_realtime_worker.py
```

首次进入 hybrid 会议时，diart worker 才会从 Hugging Face 下载或加载：

```text
pyannote/segmentation
pyannote/embedding
```

会议结束时，主后端才会加载或运行：

```text
pyannote/speaker-diarization-community-1
```

## 7. 快速自检

检查主后端 venv：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv\Scripts\python.exe -c "import numpy, importlib.metadata as m; print('main numpy', numpy.__version__); print('main pyannote.audio', m.version('pyannote.audio'))"
```

期望主后端保留 `pyannote.audio` 4.x 和 `numpy>=2`。

检查 diart venv：

```powershell
cd D:\Project\smart-meeting-assistant\backend
.\.venv-diart\Scripts\python.exe -c "import numpy, torch, importlib.metadata as m; print('diart', m.version('diart')); print('numpy', numpy.__version__); print('torch', torch.__version__); print('cuda', torch.cuda.is_available())"
```

期望 diart venv 使用：

```text
diart 0.9.2
numpy 1.26.x
torch 2.8.0
```

`cuda` 是否为 `True` 取决于你是否安装了 CUDA 版 torch。

## 8. 常见问题

### 后端启动时会不会马上下载 diart 模型

不会。diart 是懒加载，只有 hybrid 条件满足并开始会议时才会启动 worker 和加载模型。

### Volcengine 需要配置 diart 吗

不需要。Volcengine / 豆包使用 provider 原生 speaker clustering，不走 diart worker。

### `pyannote/speaker-diarization-community-1` 还有必要吗

有必要。它是会议结束后的最终确认模型。diart 的 `pyannote/segmentation` 和 `pyannote/embedding` 用于会议中的实时估计，不等价于最终 pyannote pipeline。

### 为什么要两个 venv

因为依赖冲突：

```text
主后端:
  pyannote.audio 4.x
  numpy>=2

diart worker:
  diart 0.9.2
  numpy<2
```

分开后，实时 diart 不会破坏主后端的 pyannote final diarization。

### 我已经装了 CPU 版 torch，能不能先用

可以。CPU 版能先跑通功能。如果要更低延迟，再把 `.venv-diart` 的 torch 栈换成 PyTorch 官方 CUDA wheel。
