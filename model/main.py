"""
Smart Meeting Assistant Model Service
调用阿里云语音识别服务实现实时转录和说话人分离

@author Ray
@since 1.0.0
"""

import asyncio
import logging
from typing import List

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from aliyun_asr import AliyunASRClient, TranscriptItem

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Smart Meeting Assistant Model Service", version="1.0.0")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局 ASR 客户端
asr_client = AliyunASRClient()


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("Smart Meeting Assistant Model Service 启动完成")
    logger.info("使用阿里云语音识别服务")


@app.get("/")
async def root():
    """健康检查端点"""
    return {
        "service": "Smart Meeting Assistant Model Service",
        "status": "running",
        "version": "1.0.0",
        "provider": "Aliyun ASR"
    }


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    转录音频文件（支持说话人分离）
    
    Args:
        file: 上传的音频文件
        
    Returns:
        转录结果
    """
    try:
        audio_data = await file.read()
        results = await asr_client.transcribe(audio_data)
        
        if results:
            # 返回第一条结果（兼容原有接口）
            return results[0].dict()
        else:
            return {
                "speaker": "Unknown",
                "text": "",
                "start": 0.0,
                "end": 0.0
            }
    except Exception as e:
        logger.error(f"转录请求处理失败: {e}")
        return {
            "speaker": "Error",
            "text": f"识别失败: {str(e)}",
            "start": 0.0,
            "end": 0.0
        }


@app.post("/api/transcribe/batch")
async def transcribe_batch(file: UploadFile = File(...)):
    """
    批量转录音频文件（返回所有说话人的完整结果）
    
    Args:
        file: 上传的音频文件
        
    Returns:
        完整的转录结果列表
    """
    try:
        audio_data = await file.read()
        results = await asr_client.transcribe(audio_data)
        return [result.dict() for result in results]
    except Exception as e:
        logger.error(f"批量转录请求处理失败: {e}")
        return []


@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket 实时转录端点
    
    Args:
        websocket: WebSocket 连接
    """
    await websocket.accept()
    logger.info("WebSocket 连接已建立")
    
    audio_buffer = bytearray()
    buffer_size = 1024 * 100  # 100KB 缓冲区
    
    try:
        while True:
            # 接收音频数据
            audio_chunk = await websocket.receive_bytes()
            audio_buffer.extend(audio_chunk)
            
            # 当缓冲区达到一定大小时，进行识别
            if len(audio_buffer) >= buffer_size:
                logger.info(f"处理音频缓冲区: {len(audio_buffer)} bytes")
                
                # 处理音频
                results = await asr_client.transcribe(bytes(audio_buffer))
                
                # 发送结果
                for result in results:
                    await websocket.send_json(result.dict())
                
                # 清空缓冲区
                audio_buffer.clear()
                
    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")
        
        # 处理剩余的音频数据
        if len(audio_buffer) > 0:
            try:
                results = await asr_client.transcribe(bytes(audio_buffer))
                for result in results:
                    await websocket.send_json(result.dict())
            except:
                pass
                
    except Exception as e:
        logger.error(f"WebSocket 处理错误: {e}")
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
