"""
配置文件
包含模型服务的所有配置项

@author Ray
@since 1.0.0
"""

import os
from typing import Optional


class Config:
    """应用配置类"""
    
    # 服务配置
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # 阿里云 ASR 配置
    ALIYUN_ASR_APP_KEY: str = os.getenv("ALIYUN_ASR_APP_KEY", "")
    ALIYUN_ACCESS_KEY_ID: str = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    ALIYUN_ACCESS_KEY_SECRET: str = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    
    # 音频处理配置
    SAMPLE_RATE: int = 16000
    CHUNK_DURATION: float = 30.0  # 秒
    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = Config()
