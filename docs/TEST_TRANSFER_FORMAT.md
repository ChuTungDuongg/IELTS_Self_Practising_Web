# Test transfer package format

> **Documentation audit: CURRENT.** Canonical concern này; source-check các boundary/API, không live validation.
> Mục đích: Test transfer package format. Đối chiếu source `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`: [implementation](../backend/app/schemas/transfer.py).
> Đọc cùng [current module/guide](modules/assets-transfer.md); [audit và giới hạn](DOCS_AUDIT.md). Kết quả test/benchmark ghi bên dưới thuộc lần thực hiện gốc, không phải chạy lại trong audit này.

BandPilot test packages use the format identifier `devweblocalforielts-test-bundle`. Exports without covers remain schema version 1. Exports with test covers use schema version 2. Imports accept both versions; existing version 1 packages do not require a cover.

```text
ielts-test-bundle.zip
├── manifest.json
├── tests/<source-test-uuid>.json
└── assets/<sha256>-<source-asset-uuid>.<extension>
```

The manifest lists every test JSON file and referenced asset. Version 1 `assets` entries identify their source TestVersion and include a package path, asset type, MIME type, original filename, size and SHA-256 checksum. Version 2 adds a `covers` array: each cover has its own source ID, owning `source_test_id`, safe package path, MIME type, filename, size and checksum. The corresponding test JSON references it through `cover_id`. A cover belongs to the logical Test, not to a version. Absolute local storage paths are never included.

The explicit test JSON contract contains logical tests, version numbers and lifecycle states, modules, Reading passages, Listening parts, Writing tasks (including optional structured `task_type` tags), Speaking parts and prompts, question groups, questions, configurations and answer keys. Older bundles without `task_type` import those tasks as unclassified; older modules without `speaking_parts` default to an empty list. Module durations are preserved; missing legacy durations receive canonical module defaults on import. Only referenced covers, Listening audio, question images and Writing Task images are included. Candidate Speaking recordings, transcripts and grading results are private attempt data and are excluded.

Attempts, responses, highlights, flags, events, Writing scores or feedback, History, Analytics and Full Mock sessions are excluded. This is test-content portability, not an application backup.

Before committing, import validates safe paths, file counts and expanded sizes, JSON schemas, lifecycle consistency, MIME/extension/signature, cover dimensions, byte sizes, checksums, ownership and references. All database identifiers and storage filenames are regenerated; explicit structured `question_id` references are domain-remapped. Importing the same package more than once creates independent tests and covers. A failed import compensates for files it created; if the database cannot be queried after an ambiguous commit, potentially referenced files are retained for reconciliation rather than deleted.
