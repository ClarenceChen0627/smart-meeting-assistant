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
CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[2]
PROJECT_ROOT = CURRENT_FILE.parents[3]


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    service_name: str = "Smart Meeting Assistant Backend"
    service_version: str = "2.0.0"

    ffmpeg_binary: str = os.getenv("FFMPEG_BINARY", "ffmpeg")
    sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    audio_channels: int = int(os.getenv("AUDIO_CHANNELS", "1"))
    meeting_history_db_path: str = os.getenv("MEETING_HISTORY_DB_PATH", "data/meeting_history.sqlite3")
    default_asr_provider: str = os.getenv("DEFAULT_ASR_PROVIDER", "volcengine").strip().lower() or "volcengine"

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

    volcengine_asr_app_key: str = os.getenv("VOLCENGINE_ASR_APP_KEY", "")
    volcengine_asr_access_key: str = os.getenv("VOLCENGINE_ASR_ACCESS_KEY", "")
    volcengine_asr_resource_id: str = os.getenv(
        "VOLCENGINE_ASR_RESOURCE_ID",
        "volc.seedasr.sauc.duration",
    )
    volcengine_asr_ws_url: str = os.getenv(
        "VOLCENGINE_ASR_WS_URL",
        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
    )
    volcengine_asr_nostream_ws_url: str = os.getenv(
        "VOLCENGINE_ASR_NOSTREAM_WS_URL",
        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
    )
    volcengine_asr_ssd_version: str = os.getenv("VOLCENGINE_ASR_SSD_VERSION", "200")

    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_model: str = os.getenv("DASHSCOPE_MODEL", "qwen-plus")
    dashscope_translation_model: str = os.getenv(
        "DASHSCOPE_TRANSLATION_MODEL",
        "qwen-mt-flash",
    )
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
    diarization_mode: str = os.getenv("DIARIZATION_MODE", "disabled").strip().lower() or "disabled"
    huggingface_token: str = os.getenv("HUGGINGFACE_TOKEN", "")
    diarization_model: str = os.getenv(
        "DIARIZATION_MODEL",
        "pyannote/speaker-diarization-community-1",
    )

    @property
    def asr_configured(self) -> bool:
        return bool(self.dashscope_api_key and self.dashscope_asr_model)

    @property
    def dashscope_asr_configured(self) -> bool:
        return bool(self.dashscope_api_key and self.dashscope_asr_model)

    @property
    def volcengine_asr_configured(self) -> bool:
        return bool(self.volcengine_asr_app_key and self.volcengine_asr_access_key and self.volcengine_asr_resource_id)

    @property
    def llm_configured(self) -> bool:
        return bool(self.dashscope_api_key)

    @property
    def diarization_enabled(self) -> bool:
        return self.diarization_mode == "offline"

    @property
    def resolved_meeting_history_db_path(self) -> Path:
        configured_path = Path(self.meeting_history_db_path)
        if configured_path.is_absolute():
            return configured_path
        return PROJECT_ROOT / configured_path


settings = Settings()
