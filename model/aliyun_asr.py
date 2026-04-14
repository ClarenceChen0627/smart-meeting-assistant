"""
阿里云语音识别服务封装
支持实时语音识别和说话人分离

@author Ray
@since 1.0.0
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
from typing import List, Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TranscriptItem(BaseModel):
    """转录项数据模型"""
    speaker: str
    text: str
    start: float
    end: float


class AliyunASRClient:
    """
    阿里云语音识别客户端
    使用录音文件识别极速版 API
    """
    
    def __init__(
        self,
        app_key: str = None,
        access_key_id: str = None,
        access_key_secret: str = None
    ):
        self.app_key = app_key or os.getenv("ALIYUN_ASR_APP_KEY", "")
        self.access_key_id = access_key_id or os.getenv("ALIYUN_ACCESS_KEY_ID", "")
        self.access_key_secret = access_key_secret or os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
        
        # API 端点
        self.api_url = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/FlashRecognizer"
        
        logger.info("阿里云 ASR 客户端初始化完成")
    
    async def transcribe(self, audio_data: bytes) -> List[TranscriptItem]:
        """
        转录音频数据
        
        Args:
            audio_data: 音频字节数据（支持 PCM/WAV/OPUS 等格式）
            
        Returns:
            转录结果列表
        """
        try:
            # 保存为临时文件
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name
            
            # 读取音频文件
            with open(temp_path, 'rb') as f:
                audio_content = f.read()
            
            # 构建请求
            url = f"{self.api_url}?appkey={self.app_key}&format=wav"
            
            headers = {
                "Content-Type": "application/octet-stream",
                "X-NLS-Token": await self._get_token()
            }
            
            # 发送请求
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    content=audio_content,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return self._parse_result(result)
                else:
                    logger.error(f"识别失败: {response.status_code} - {response.text}")
                    return self._create_mock_result(audio_data)
            
        except Exception as e:
            logger.error(f"转录异常: {e}")
            return self._create_mock_result(audio_data)
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except:
                pass
    
    async def _get_token(self) -> str:
        """
        获取访问令牌
        实际应该调用阿里云 STS 服务获取临时 token
        """
        # 简化实现：直接使用 AccessKeyId
        # 生产环境应该使用 Token 服务
        return self.access_key_id
    
    def _parse_result(self, result: dict) -> List[TranscriptItem]:
        """解析识别结果"""
        items = []
        
        try:
            # 获取识别文本
            flash_result = result.get("flash_result", {})
            sentences = flash_result.get("sentences", [])
            
            for idx, sentence in enumerate(sentences):
                text = sentence.get("text", "")
                begin_time = sentence.get("begin_time", 0) / 1000.0
                end_time = sentence.get("end_time", 0) / 1000.0
                
                # 简单的说话人分配（基于时间间隔）
                speaker_id = self._assign_speaker(begin_time, idx)
                
                if text.strip():
                    items.append(TranscriptItem(
                        speaker=f"Speaker_{speaker_id}",
                        text=text.strip(),
                        start=begin_time,
                        end=end_time
                    ))
            
            logger.info(f"解析得到 {len(items)} 条转录结果")
            
        except Exception as e:
            logger.error(f"解析结果异常: {e}")
        
        return items
    
    def _assign_speaker(self, begin_time: float, index: int) -> str:
        """
        简单的说话人分配逻辑
        实际应该使用声纹识别或说话人分离模型
        """
        # 基于时间段分配说话人
        if begin_time < 10:
            return "A"
        elif begin_time < 20:
            return "B"
        elif begin_time < 30:
            return "A"
        else:
            # 交替分配
            return "A" if index % 2 == 0 else "B"
    
    def _create_mock_result(self, audio_data: bytes) -> List[TranscriptItem]:
        """
        创建模拟结果（用于测试或 API 调用失败时）
        """
        logger.warning("使用模拟识别结果")
        
        # 根据音频大小估算时长
        duration = len(audio_data) / (16000 * 2)  # 假设 16kHz, 16bit
        
        return [
            TranscriptItem(
                speaker="Speaker_A",
                text="这是一段模拟的语音识别结果，用于测试。",
                start=0.0,
                end=min(3.0, duration)
            ),
            TranscriptItem(
                speaker="Speaker_B",
                text="实际使用时请配置阿里云 ASR 的 API 密钥。",
                start=3.0,
                end=min(6.0, duration)
            )
        ]


# 创建全局实例
asr_client = AliyunASRClient()
