# Changelog

## Unreleased

- Added self-hosted deployment guidance, release checklist, and smoke testing documentation.
- Added a read-only backend configuration check command.
- Added optional API token protection for private deployments.
- Added configurable CORS, security response headers, and upload size/type limits.
- Added meeting history search/filter UI with favorites, archive state, and tags.
- Added a cross-meeting Memory workspace with project/tag collections, action item rollups, decision/risk/open-question tracking, and next-meeting briefs.
- Added `GET /api/memory` for SQLite-backed cross-meeting memory aggregation.
- Added a dependency-free real-browser Memory workspace smoke test command.
- Added Markdown export variants for standard notes, Chinese minutes, and action-item-only delivery.
- Added participant-level analysis details for speaker sentiment, engagement, speaking time, and interaction signals.
- Split frontend production vendor chunks for charts, icons, Radix UI, and shared vendor code to reduce oversized entry bundles.
- Renamed frontend package metadata away from the original scaffold name.
- Hardened raw upload audio retention filenames for Windows reserved names and long sanitized filenames.
- Added compact audit events for meeting deletion and a `meeting_id` filter on the audit event API.
- Improved responsive layouts for analysis, action items, and meeting history panels on narrow screens.
- Fixed workspace tab overflow on narrow screens when the audit tab is visible.
- Normalized prompted meeting tags on the frontend to match backend limits before saving.
- Added audit events for meeting favorite, archive, and tag metadata updates.
