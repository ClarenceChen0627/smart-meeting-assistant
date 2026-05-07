export const processingStageLabels = {
  transcribing: 'Transcribing uploaded audio',
  translating: 'Generating transcript translations',
  analyzing: 'Analyzing meeting dynamics',
  summarizing: 'Generating meeting summary',
};

export const buildUploadStatusMessage = (meeting, isUploadingFile) => {
  if (isUploadingFile) {
    return 'Uploading audio file...';
  }

  if (!meeting) {
    return 'Select a meeting audio file to generate transcript, summary, action items, and analysis.';
  }

  if (meeting.status === 'processing') {
    return meeting.processing_stage
      ? processingStageLabels[meeting.processing_stage]
      : 'Processing uploaded meeting...';
  }

  if (meeting.status === 'failed') {
    return meeting.error_message || 'Upload processing failed.';
  }

  return 'Upload meeting is ready to review.';
};
