import assert from 'node:assert/strict';

import { buildUploadStatusMessage, processingStageLabels } from '../src/app/uploadStatus.js';

const test = (name, fn) => {
  fn();
  console.log(`ok - ${name}`);
};

test('buildUploadStatusMessage reports upload input state', () => {
  assert.equal(buildUploadStatusMessage(null, true), 'Uploading audio file...');
  assert.equal(
    buildUploadStatusMessage(null, false),
    'Select a meeting audio file to generate transcript, summary, action items, and analysis.'
  );
});

test('buildUploadStatusMessage reports processing stages', () => {
  assert.equal(
    buildUploadStatusMessage({ status: 'processing', processing_stage: 'analyzing' }, false),
    processingStageLabels.analyzing
  );
  assert.equal(
    buildUploadStatusMessage({ status: 'processing', processing_stage: null }, false),
    'Processing uploaded meeting...'
  );
});

test('buildUploadStatusMessage reports terminal upload states', () => {
  assert.equal(
    buildUploadStatusMessage({ status: 'failed', error_message: 'Audio conversion failed' }, false),
    'Audio conversion failed'
  );
  assert.equal(
    buildUploadStatusMessage({ status: 'failed', error_message: '' }, false),
    'Upload processing failed.'
  );
  assert.equal(
    buildUploadStatusMessage({ status: 'finalized' }, false),
    'Upload meeting is ready to review.'
  );
});
