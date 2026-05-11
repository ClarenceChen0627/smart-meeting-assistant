from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.clients.dashscope_asr_client import DashScopeASRClient
from app.clients.dashscope_client import DashScopeClient
from app.clients.demo_dashscope_client import DemoDashScopeClient
from app.clients.demo_asr_client import DemoASRClient
from app.clients.volcengine_asr_client import VolcengineASRClient
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.asr_provider_service import ASRProviderService
from app.services.audio_codec_service import AudioCodecService
from app.services.diarization_service import DiarizationService
from app.services.glossary_service import GlossaryService
from app.services.glossary_store_service import GlossaryStoreService
from app.services.meeting_analysis_service import MeetingAnalysisService
from app.services.meeting_history_service import MeetingHistoryService
from app.services.raw_audio_retention_service import RawAudioRetentionService
from app.services.observability_service import ObservabilityService
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService
from app.services.upload_meeting_service import UploadMeetingService
from app.services.upload_queue_service import UploadQueueStore

logger = logging.getLogger(__name__)


async def run_worker(*, once: bool) -> int:
    dashscope_asr_client = DashScopeASRClient(settings)
    volcengine_asr_client = VolcengineASRClient(settings)
    demo_asr_client = DemoASRClient(settings)
    dashscope_client = DemoDashScopeClient(settings) if settings.demo_mode else DashScopeClient(settings)
    speaker_service = SpeakerService()
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    upload_queue_store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
        max_attempts=settings.upload_queue_max_attempts,
        retry_base_seconds=settings.upload_queue_retry_base_seconds,
        retry_max_seconds=settings.upload_queue_retry_max_seconds,
    )
    upload_meeting_service = UploadMeetingService(
        asr_provider_service=ASRProviderService(
            settings=settings,
            dashscope_client=dashscope_asr_client,
            volcengine_client=volcengine_asr_client,
            demo_client=demo_asr_client,
        ),
        audio_codec_service=AudioCodecService(settings),
        speaker_service=speaker_service,
        diarization_service=DiarizationService(settings, speaker_service),
        summary_service=SummaryService(dashscope_client),
        meeting_analysis_service=MeetingAnalysisService(dashscope_client),
        translation_service=TranslationService(dashscope_client),
        meeting_history_service=meeting_history_service,
        glossary_service=GlossaryService(
            settings,
            GlossaryStoreService(settings.resolved_meeting_history_db_path),
        ),
        raw_audio_retention_service=RawAudioRetentionService(settings),
        upload_queue_store=upload_queue_store,
        embedded_worker_enabled=False,
        upload_queue_processing_timeout_seconds=settings.upload_queue_processing_timeout_seconds,
        observability_service=ObservabilityService(),
    )

    try:
        if once:
            processed_count = await upload_meeting_service.process_available_jobs()
            logger.info("Processed %s upload job(s).", processed_count)
        else:
            upload_meeting_service.start_embedded_worker()
            logger.info("Upload worker is running. Press Ctrl+C to stop.")
            await asyncio.Event().wait()
    finally:
        await upload_meeting_service.shutdown()
        await dashscope_asr_client.aclose()
        await volcengine_asr_client.aclose()
        await demo_asr_client.aclose()
        await dashscope_client.aclose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the persistent upload queue worker.")
    parser.add_argument("--once", action="store_true", help="Process currently queued jobs and exit.")
    args = parser.parse_args()
    configure_logging(settings.log_level)
    try:
        return asyncio.run(run_worker(once=args.once))
    except KeyboardInterrupt:
        logger.info("Upload worker stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
