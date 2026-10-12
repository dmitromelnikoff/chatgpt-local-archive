# Changelog

This document starts at the first proposed public GitHub baseline. Historical update notes below are derived from the preserved release materials and conversation history, **not from pre-existing Git commits**. No historical Git commit dates have been fabricated.

## [Unreleased]

- No changes yet.

## [7.3.16.1] — 2026-10-12

- Consolidated a single installable source package for clean builds.
- Fixed serving of the per-chat metadata JavaScript asset from the local server.
- Fixed Markdown download names to use the real conversation title (Unicode preserved; filename sanitized for Windows).
- Includes the v7.3.16 prompt/code/conversation copy actions, Markdown export, original chat links and list metadata.
- Includes the v7.3.15 calendar and summary statistics.
- Retains the v7.3.14 attachment recovery and best-effort DIL/Intelligent UI viewer.
- Preserves one-time build protection against accidentally replacing an existing archive.

### Prior development milestones (documentation only)

| Milestone | Known change |
| --- | --- |
| 7.2–7.2.2 | Better binding of Library assets using graph relationships and synthetic generated-image entries where justified. |
| 7.3–7.3.3 | Browser-assisted restoration of missing files; preservation of the full generated-files listing; recovery-link fixes. |
| 7.3.4–7.3.7 | Copy assistant replies; question navigation; service-block visibility switch; image/download link role fixes. |
| 7.3.8–7.3.14 | Intelligent UI / Markdown switch, constrained template expansion, DIL formatting patches. |
| 7.3.15 | Calendar and statistics. |
| 7.3.16 | Copy prompts, code, entire chats; Markdown export, original links and left-side counters. |

For more specific evidence and known limitations, see the preserved [Russian development history](docs/PROJECT_HISTORY_RU.md) and [7.3.16.1 addendum](docs/PROJECT_HISTORY_ADDENDUM_73161_RU.md).
