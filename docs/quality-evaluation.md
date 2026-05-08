# Quality Evaluation

Language:
- English: `quality-evaluation.md`
- 简体中文: [zh/quality-evaluation.md](zh/quality-evaluation.md)

Use the upload quality evaluator to run repeatable local checks against real provider output. The evaluator is intentionally local-only: real audio, private manifests, and generated reports should stay under `data/evals/`, which is ignored by Git.

## What It Checks

The first version covers the upload meeting workflow. Each manifest case can verify:

- upload completion status and unexpected provider fallback
- transcript row count and required / forbidden terminology
- speaker count and final speaker labels
- translated transcript fields for the selected target language
- non-empty summary, action items, and analysis
- optional WER / CER against a human-reviewed reference transcript

The generated Markdown report includes manual review fields for quality judgments that should not be reduced to a simple automated score, such as speaker reasonableness and summary usefulness.

## Prepare Private Data

1. Copy the example manifest:

   ```powershell
   New-Item -ItemType Directory -Force data\evals\audio
   Copy-Item docs\examples\upload-quality.manifest.example.json data\evals\upload-quality.local.json
   ```

2. Put private audio files under `data/evals/audio/`.
3. Edit `data/evals/upload-quality.local.json` so each `audio_path` is relative to the manifest file.
4. Add real glossary terms, expected terminology, speaker expectations, and optional reference transcripts.

Do not commit private audio, local manifests, or generated reports.

## Run The Evaluator

Start the backend with real provider credentials and an isolated history database:

```powershell
$env:MEETING_HISTORY_DB_PATH='..\data\evals\meeting_history.sqlite3'
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

In a second terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe tools\evaluate_upload_quality.py --manifest ..\data\evals\upload-quality.local.json --api-base-url http://localhost:8080 --output-dir ..\data\evals\reports
```

The evaluator writes a timestamped report directory containing:

- `report.json`: structured check results for automation and comparison.
- `report.md`: a review-friendly summary with manual review fields.
- `cases/*.meeting.json`: raw `MeetingRecord` API responses for debugging.

## Manifest Fields

- `id`: stable case identifier.
- `audio_path`: private audio path, absolute or relative to the manifest file.
- `scene`: meeting scene, such as `general`, `finance`, or `hr`.
- `provider`: expected ASR provider, such as `volcengine` or `dashscope`.
- `target_lang`: optional translation target.
- `glossary_terms`: string or array of terms; entries can use `term=>replacement`.
- `allow_provider_fallback`: defaults to `false` so accidental demo fallback fails the run.
- `expected`: automated checks, including transcript count, terminology, speakers, translations, summary, action items, analysis, and optional WER / CER thresholds.

The evaluator does not start FastAPI and does not run in CI by default.
