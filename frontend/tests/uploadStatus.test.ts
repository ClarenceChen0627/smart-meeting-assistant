import { describe, expect, it } from 'vitest';

import { asrProviderOptions } from '../src/app/asrProviders';
import { buildUploadStatusMessage, processingStageLabels } from '../src/app/uploadStatus';

describe('buildUploadStatusMessage', () => {
  it('reports upload input state', () => {
    expect(buildUploadStatusMessage(null, true)).toBe('Uploading audio file...');
    expect(buildUploadStatusMessage(null, false)).toBe(
      'Select a meeting audio file to generate transcript, summary, action items, and analysis.'
    );
  });

  it('reports processing stages', () => {
    expect(
      buildUploadStatusMessage({ status: 'processing', processing_stage: 'analyzing' }, false)
    ).toBe(processingStageLabels.analyzing);
    expect(
      buildUploadStatusMessage({ status: 'processing', processing_stage: null }, false)
    ).toBe('Processing uploaded meeting...');
  });

  it('reports terminal upload states', () => {
    expect(
      buildUploadStatusMessage({ status: 'failed', error_message: 'Audio conversion failed' }, false)
    ).toBe('Audio conversion failed');
    expect(
      buildUploadStatusMessage({ status: 'failed', error_message: '' }, false)
    ).toBe('Upload processing failed.');
    expect(buildUploadStatusMessage({ status: 'finalized' }, false)).toBe(
      'Upload meeting is ready to review.'
    );
  });
});

describe('ASR provider options', () => {
  it('exposes demo mode as a local workflow', () => {
    const providerCodes = asrProviderOptions.map((provider) => provider.code);
    expect(providerCodes).toEqual(['volcengine', 'dashscope', 'demo']);

    const demoProvider = asrProviderOptions.find((provider) => provider.code === 'demo');
    expect(demoProvider).toBeDefined();
    expect(demoProvider?.name).toBe('Demo Mode');
    expect(demoProvider?.badge).toBe('Local');
    expect(demoProvider?.description).toMatch(/DEMO_MODE=1/);
  });
});
