from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_env_files() -> None:
    current = Path(__file__).resolve()
    backend_root = current.parents[2]
    project_root = current.parents[3]

    for env_path in (
        project_root / ".env",
        backend_root / ".env",
    ):
        if env_path.exists():
            load_dotenv(env_path, override=False)


_load_env_files()


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    service_name: str = "Smart Meeting Assistant Backend"
    service_version: str = "2.0.0"

    summary_interval: int = int(os.getenv("SUMMARY_INTERVAL", "10"))
    ffmpeg_binary: str = os.getenv("FFMPEG_BINARY", "ffmpeg")
    sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    audio_channels: int = int(os.getenv("AUDIO_CHANNELS", "1"))

    aliyun_asr_app_key: str = os.getenv("ALIYUN_ASR_APP_KEY", "")
    aliyun_nls_token: str = os.getenv("ALIYUN_NLS_TOKEN", "")
    aliyun_access_key_id: str = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    aliyun_access_key_secret: str = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    aliyun_asr_url: str = os.getenv(
        "ALIYUN_ASR_URL",
        "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/FlashRecognizer",
    )
    aliyun_token_url: str = os.getenv(
        "ALIYUN_TOKEN_URL",
        "https://nls-meta.cn-shanghai.aliyuncs.com/",
    )
    aliyun_region_id: str = os.getenv("ALIYUN_REGION_ID", "cn-shanghai")

    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_model: str = os.getenv("DASHSCOPE_MODEL", "qwen-plus")
    dashscope_chat_url: str = os.getenv(
        "DASHSCOPE_CHAT_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    dashscope_asr_model: str = os.getenv("DASHSCOPE_ASR_MODEL", "paraformer-realtime-v1")
    dashscope_asr_ws_url: str = os.getenv(
        "DASHSCOPE_ASR_WS_URL",
        "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
    )
    dashscope_workspace_id: str = os.getenv("DASHSCOPE_WORKSPACE_ID", "")

    @property
    def asr_configured(self) -> bool:
        return bool(self.dashscope_api_key and self.dashscope_asr_model)

    @property
    def llm_configured(self) -> bool:
        return bool(self.dashscope_api_key)


settings = Settings()
