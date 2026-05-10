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


def _configure_huggingface_cache() -> None:
    for env_name in ("HF_HOME", "HF_HUB_CACHE", "PYANNOTE_CACHE"):
        configured = os.getenv(env_name, "").strip()
        if not configured:
            continue
        cache_path = Path(configured).expanduser()
        if not cache_path.is_absolute():
            cache_path = PROJECT_ROOT / cache_path
        os.environ[env_name] = str(cache_path.resolve())


_configure_huggingface_cache()


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    service_name: str = "Smart Meeting Assistant Backend"
    service_version: str = "2.0.0"
    demo_mode: bool = _env_flag("DEMO_MODE", False)

    ffmpeg_binary: str = os.getenv("FFMPEG_BINARY", "ffmpeg")
    sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    audio_channels: int = int(os.getenv("AUDIO_CHANNELS", "1"))
    meeting_history_db_path: str = os.getenv("MEETING_HISTORY_DB_PATH", "data/meeting_history.sqlite3")
    raw_audio_retention_enabled: bool = _env_flag("RAW_AUDIO_RETENTION_ENABLED", True)
    raw_audio_dir: str = os.getenv("RAW_AUDIO_DIR", "data/raw_audio")
    upload_queue_dir: str = os.getenv("UPLOAD_QUEUE_DIR", "data/upload_queue")
    upload_queue_embedded_worker_enabled: bool = _env_flag("UPLOAD_QUEUE_EMBEDDED_WORKER_ENABLED", True)
    upload_queue_max_attempts: int = int(os.getenv("UPLOAD_QUEUE_MAX_ATTEMPTS", "3"))
    upload_queue_retry_base_seconds: float = float(os.getenv("UPLOAD_QUEUE_RETRY_BASE_SECONDS", "30"))
    upload_queue_retry_max_seconds: float = float(os.getenv("UPLOAD_QUEUE_RETRY_MAX_SECONDS", "300"))
    upload_queue_processing_timeout_seconds: float = float(os.getenv("UPLOAD_QUEUE_PROCESSING_TIMEOUT_SECONDS", "1800"))
    custom_glossary_terms: str = os.getenv("CUSTOM_GLOSSARY_TERMS", "")
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
    realtime_diarization_duration_seconds: float = float(os.getenv("REALTIME_DIARIZATION_DURATION_SECONDS", "5"))
    realtime_diarization_step_seconds: float = float(os.getenv("REALTIME_DIARIZATION_STEP_SECONDS", "0.5"))
    realtime_diarization_latency_seconds: float = float(os.getenv("REALTIME_DIARIZATION_LATENCY_SECONDS", "1"))
    diart_segmentation_model: str = os.getenv("DIART_SEGMENTATION_MODEL", "pyannote/segmentation").strip() or "pyannote/segmentation"
    diart_embedding_model: str = os.getenv("DIART_EMBEDDING_MODEL", "pyannote/embedding").strip() or "pyannote/embedding"
    diart_python_path: str = os.getenv("DIART_PYTHON_PATH", "").strip()

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
        return self.diarization_mode in {"offline", "hybrid"}

    @property
    def realtime_diarization_enabled(self) -> bool:
        return self.diarization_mode == "hybrid"

    @property
    def resolved_meeting_history_db_path(self) -> Path:
        configured_path = Path(self.meeting_history_db_path)
        if configured_path.is_absolute():
            return configured_path
        return PROJECT_ROOT / configured_path

    @property
    def resolved_raw_audio_dir(self) -> Path:
        configured_path = Path(self.raw_audio_dir)
        if configured_path.is_absolute():
            return configured_path
        return PROJECT_ROOT / configured_path

    @property
    def resolved_upload_queue_dir(self) -> Path:
        configured_path = Path(self.upload_queue_dir)
        if configured_path.is_absolute():
            return configured_path
        return PROJECT_ROOT / configured_path


settings = Settings()
