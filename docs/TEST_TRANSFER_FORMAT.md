# Test transfer package format

IELTS Studio test packages use the format name `devweblocalforielts-test-bundle` and schema version `1`.

```text
ielts-test-bundle.zip
├── manifest.json
├── tests/<source-test-uuid>.json
└── assets/<sha256>-<source-asset-uuid>.<extension>
```

`manifest.json` lists every test JSON file and referenced asset. Asset entries contain the portable package path, source identifiers, asset type, MIME type, original filename, byte size, and SHA-256 checksum. Absolute local storage paths are never included.

The explicit test JSON contract contains logical tests, all version numbers and lifecycle states, modules, Reading passages, Listening parts, Writing tasks, question groups, questions, configurations, and answer keys. Only referenced Listening audio, question images, and Writing Task images are included.

Attempts, responses, highlights, flags, events, Writing scores or feedback, History, Analytics, and Full Mock sessions are excluded. This is test-content portability, not an application backup.

Import accepts schema version 1 only. It validates archive paths, file count and expanded size, JSON schemas, version lifecycle consistency, MIME/extension/signature, byte size, checksums, asset ownership, and question references before committing. All database identifiers and storage filenames are regenerated; explicit structured `question_id` references are domain-remapped. Importing the same package more than once creates independent logical tests.
