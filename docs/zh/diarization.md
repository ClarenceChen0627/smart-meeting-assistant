# Speaker Diarization

Language:
- English: [../diarization.md](../diarization.md)
- 简体中文: `diarization.md`

Speaker diarization 是可选能力。如果它被关闭或不可用，会议仍然可以运行，speaker label 会保留 provider 返回值或显示为 `Unknown`。

Windows 下详细 diart 配置见 [diart Setup](../diart.md) 或 [diart Setup 中文版](diart.md)。

## Modes

| Mode | Value | Behavior |
| --- | --- | --- |
| Disabled | `DIARIZATION_MODE=disabled` | 不运行后端 pyannote/diart。Volcengine 原生 speaker 输出仍可出现。 |
| Offline | `DIARIZATION_MODE=offline` | DashScope transcript 在会议结束后做 speaker 确认。 |
| Hybrid | `DIARIZATION_MODE=hybrid` | DashScope 会议中通过 diart 推送临时 speaker update，finalize 后再用 pyannote 确认。 |

Hybrid mode 只适用于 DashScope `paraformer-realtime-v1`。Volcengine speaker clustering 来自 provider 路径。

## Required Variables

```env
DIARIZATION_MODE=offline
HUGGINGFACE_TOKEN=your-hf-token
HF_HOME=models/huggingface
PYANNOTE_CACHE=models/huggingface/hub
HF_HUB_DISABLE_SYMLINKS=1
HF_HUB_OFFLINE=0
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
DIARIZATION_MODEL=pyannote/speaker-diarization-community-1
```

Hybrid mode：

```env
DIARIZATION_MODE=hybrid
REALTIME_DIARIZATION_DURATION_SECONDS=5
REALTIME_DIARIZATION_STEP_SECONDS=0.5
REALTIME_DIARIZATION_LATENCY_SECONDS=1
DIART_SEGMENTATION_MODEL=pyannote/segmentation
DIART_EMBEDDING_MODEL=pyannote/embedding
DIART_PYTHON_PATH=D:\Project\smart-meeting-assistant\backend\.venv-diart\Scripts\python.exe
```

## Optional diart Worker Environment

`diart==0.9.2` 需要 `numpy<2`，而主后端 pyannote stack 可能需要更新的依赖。建议把实时 diart 放在独立环境：

```powershell
cd backend
.\.venv\Scripts\python.exe -m venv .venv-diart
.\.venv-diart\Scripts\python.exe -m pip install -i https://pypi.org/simple -r requirements-diart.txt
```

然后把 `DIART_PYTHON_PATH` 指向 `.venv-diart` 的 Python 可执行文件。

## Windows Cache Notes

- `HF_HOME=models/huggingface` 把模型下载放在项目内。
- `PYANNOTE_CACHE=models/huggingface/hub` 让 pyannote 复用项目内 cache。
- `HF_HUB_DISABLE_SYMLINKS=1` 避免 Windows symlink 权限问题。
- 所需模型全部下载后，可以设置 `HF_HUB_OFFLINE=1` 避免重复 Hugging Face 网络检查。
- 第一次下载或更换模型时，把 `HF_HUB_OFFLINE=0`。

## Limitations

- Hybrid speaker label 在采集中是临时结果，可能跳变。
- DashScope diarization mode 下，finalize 后的 pyannote label 才是最终结果。
- CPU-only Windows 机器上 diarization 可能比较慢。
- Demo mode 不运行 diarization；它返回固定 speaker label。
