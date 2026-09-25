# Structured Draft Import (`ielts-draft-import-v1`)

Draft Import accepts text and answer data that has already been transcribed from screenshots or scans. It does not run OCR or AI inference. The command creates one new `Test`, version 1, in `DRAFT` status. Open the reported Builder URL to review and publish through the normal workflow.

A ready-to-run fictional manifest is in [docs/examples/draft-import-manifest.json](examples/draft-import-manifest.json).

From `backend/`:

```sh
uv run python -m app.import_draft path/to/manifest.json
```

Asset paths are relative to the directory containing `manifest.json`. Keep them in an `assets/` subdirectory. The importer rejects absolute paths, `..` traversal, missing files, unsupported extensions, malformed file signatures, and files above the existing upload size limits. It copies accepted files through `LocalAssetStorage` and links them to the new version. On a failed import, the database transaction rolls back and copied files are removed.

## Manifest

```json
{
  "format": "ielts-draft-import-v1",
  "title": "Fictional IELTS Practice Test",
  "description": "Optional source notes",
  "modules": []
}
```

`modules` contains any combination of one `READING`, one `LISTENING`, and one `WRITING` module. The importer rejects duplicate module types. Titles are optional on modules. `recommended_duration_seconds` is optional; omitted values default to 3600 for Reading, 1800 for Listening, and 3600 for Writing. Explicit positive values are preserved. Questions and passage blocks do not need UUIDs; the importer generates them and keeps them stable through Builder fetch and save.

Set `"allow_incomplete": true` only when the source has no answer key or some question numbers cannot yet be represented. In this mode, omitted answers are stored as empty keys, and explicit question-number gaps are kept in the unpublished draft. Other structural validation still applies. The draft remains unpublishable until keys and numbering are resolved. The default is `false`.

### Reading

Reading has `passages`. Each passage has a `title`, one or more `blocks`, and zero or more `question_groups`. A block is a `heading` or `paragraph` with `text`. Paragraph `label` is optional; missing labels are generated A, B, C, and so on. A supplied label is preserved. Matching Headings targets use `"Paragraph A"` or `"A"` and must resolve to exactly one paragraph.

### Listening

Listening has up to four `sections`; these become Builder Listening Parts. Each section has a `title` and `question_groups`. A module-level `audio` path is optional. The current single shared Listening audio asset remains the only audio model. Missing audio produces a Draft warning.

### Writing

Writing has `tasks`, each with `task_number` 1 or 2, `prompt`, optional `task_type`, and optional `minimum_recommended_words`. `task_type` is a structured authoring tag, not an official IELTS taxonomy. Task 1 accepts `LINE_GRAPH`, `BAR_CHART`, `PIE_CHART`, `TABLE`, `MIXED_CHARTS`, `PROCESS`, `MAP_PLAN`, `OBJECT_SYSTEM_DIAGRAM`, or `OTHER_VISUAL`. Task 2 accepts `OPINION`, `DISCUSS_BOTH_VIEWS`, `DISCUSS_BOTH_VIEWS_AND_OPINION`, `ADVANTAGES_DISADVANTAGES`, `ADVANTAGES_OUTWEIGH_DISADVANTAGES`, `PROBLEM_SOLUTION`, `CAUSE_SOLUTION`, `TWO_PART_QUESTION`, or `OTHER_ESSAY`. Omit `task_type` to leave it unclassified; the importer does not infer it from prompt text. Task 1 may contain an `image` path. Task 2 cannot have an image. A missing task is represented by the Builder's fixed empty task slot and reported as a warning. The standard word guidance is 150 for Task 1 and 250 for Task 2 unless supplied otherwise.

## Question groups

Use the exact `question_type` names from the current question registry:

`multiple_choice`, `multiple_choice_multiple`, `true_false_not_given`, `yes_no_not_given`, `text_completion`, `matching_headings`, `matching`, `matching_information`, `matching_features`, `matching_sentence_endings`, `summary_completion_word_list`, `plan_labelling`, `map_labelling`, `diagram_labelling`, `form_completion`, `note_completion`, `table_completion`, `flow_chart_completion`, `summary_completion`, `sentence_completion`, and `short_answer`.

Each group may have an `instruction`. Missing instructions are allowed with a warning. For ordinary questions, supply `questions` with `prompt` and `answer`. A `number` is optional; missing numbers are assigned in order within the module. Explicit numbers are preserved, but the complete module must number questions exactly 1 through N, without gaps or duplicates, and must stay within 1–40. Ambiguous or invalid numbering is fatal unless `allow_incomplete` is true; duplicates are always fatal.

For `true_false_not_given`, answers are `TRUE`, `FALSE`, or `NOT_GIVEN`; for `yes_no_not_given`, they are `YES`, `NO`, or `NOT_GIVEN`. Case and simple whitespace variants are normalized by the existing question system. Invalid values are fatal.

For `multiple_choice`, each question has `options` such as `[{"key":"A","text":"River"},{"key":"B","text":"Hill"}]`, and its `answer` is a key such as `"A"`. `multiple_choice_multiple` uses an array, for example `"answer": ["A", "B"]`. A shared multi-select question consumes one IELTS number per required selection. Set equal `min_selections` and `max_selections` when the answer is omitted, or provide `number` and inclusive `end_number` (for example 13 and 14); the importer validates that the range and selection count agree. The next question starts after that range. Candidate answers are unordered.

For `matching_headings`, put `options` at group level and give each question a `target` such as `"Paragraph A"` and an `answer` option key. `matching`, `matching_features`, and `matching_sentence_endings` use group options and question answers the same way. `matching_information` uses a paragraph label such as `"A"` as the answer and resolves it to its block ID. `allow_option_reuse` is available on matching groups.

For `short_answer` and text answers, `answer` is a string or an array of accepted alternatives. `max_words` and `max_numbers` may be set per question. The server's registered evaluator remains authoritative.

## `{{gap}}` completion

Use `content` and one `answers` item per `{{gap}}`, in reading order. `numbers` is an optional array of explicit question numbers. Alternatively, use `questions` with one answer per gap. Do not supply both `answers` and `questions`.

```json
{
  "question_type": "note_completion",
  "content": ["Course benefits:", "good {{gap}}", "close to {{gap}}"],
  "answers": ["reputation", "home"]
}
```

`text_completion`, `summary_completion_word_list`, `note_completion`, `form_completion`, `flow_chart_completion`, `summary_completion`, and `sentence_completion` use string lines. `table_completion` uses `content` as rows of string cells, for example `[["Place", "Feature"], ["River", "{{gap}}"]]`; `columns` supplies the matching column labels or defaults to `Column 1`, `Column 2`, etc. `summary_completion_word_list` also needs group `options`, and each answer is an option key.

The importer turns each marker into one structured GAP with a generated ID linked to one generated question ID. Text around gaps stays in order. Multiple gaps in one line, adjacent gaps, and gaps at the start or end are supported. Text, note, and table segment models retain empty boundary text where their canonical structure needs it. Literal markers are not saved in those structured layouts. The exception is `diagram_labelling`, whose existing Builder prompt format intentionally uses one literal `{{gap}}` per diagram question.

## Images and audio

`plan_labelling` and `map_labelling` require group `image`, group `options`, and question answers. Reading questions also need normalized `x` and `y` marker positions between 0 and 1. Listening's current visual model does not store markers. `diagram_labelling` requires group `image` and, for each question, `box` (`x`, `y`, `width`) and `arrow` (`start_x`, `start_y`, `end_x`, `end_y`) using normalized coordinates. A diagram question's `prompt` receives one `{{gap}}` if it does not already have one. Writing Task 1 can have `image`; Listening can have one module-level `audio`.

Supported images: PNG, JPEG, WebP. Supported audio: MP3, M4A, AAC, WAV, Ogg. File content must match its extension.

## Validation

Fatal errors stop the import and leave no test or copied asset: invalid JSON/schema, unknown question types, invalid answers, duplicate or noncanonical numbers, missing matching targets, mismatched gap and answer counts, unsafe or malformed assets, and any structural Builder validation error. The message includes the manifest path or Builder field that needs correction.

Readiness warnings are printed with a successful Draft: missing Listening audio, fewer than three Reading passages or four Listening sections, fewer than 40 questions in a Reading or Listening module, incomplete Writing tasks, and missing group instructions. The administrator should review OCR ambiguity, paragraph labels, answer keys, visual marker placement, diagram geometry, and audio synchronization before publishing.

## Complete fictional example

Save this as `manifest.json` beside `assets/fictional-chart.png` if you want to include the optional image. Remove the `image` property to run the example without any asset.

```json
{
  "format": "ielts-draft-import-v1",
  "title": "Fictional River Town Practice",
  "description": "Entirely invented practice material.",
  "modules": [
    {
      "type": "READING",
      "title": "Reading",
      "passages": [
        {
          "title": "The Imaginary River Town",
          "blocks": [
            {"type": "heading", "text": "A town made for a story"},
            {"type": "paragraph", "label": "A", "text": "River Town is a fictional place beside a blue canal. Its library opened in 2012."},
            {"type": "paragraph", "label": "B", "text": "Residents use small boats to visit the library after sunset."}
          ],
          "question_groups": [
            {
              "question_type": "true_false_not_given",
              "instruction": "Do the statements agree with the passage?",
              "questions": [
                {"number": 1, "prompt": "River Town is a real city.", "answer": "FALSE"},
                {"number": 2, "prompt": "The library opened in 2012.", "answer": "TRUE"}
              ]
            },
            {
              "question_type": "matching_headings",
              "instruction": "Match each paragraph to a heading.",
              "options": [
                {"key": "i", "text": "The town and its library"},
                {"key": "ii", "text": "Evening journeys"}
              ],
              "questions": [
                {"number": 3, "target": "Paragraph A", "answer": "i"},
                {"number": 4, "target": "Paragraph B", "answer": "ii"}
              ]
            },
            {
              "question_type": "note_completion",
              "instruction": "Complete the notes.",
              "content": ["Library opened in {{gap}}", "Residents travel by {{gap}}"],
              "answers": ["2012", "boat"]
            }
          ]
        }
      ]
    },
    {
      "type": "LISTENING",
      "title": "Listening",
      "sections": [
        {
          "title": "Section 1",
          "question_groups": [
            {
              "question_type": "multiple_choice",
              "instruction": "Choose one answer.",
              "questions": [
                {
                  "number": 1,
                  "prompt": "Where will the fictional meeting take place?",
                  "options": [
                    {"key": "A", "text": "The library"},
                    {"key": "B", "text": "The canal bridge"}
                  ],
                  "answer": "A"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "WRITING",
      "tasks": [
        {"task_number": 1, "task_type": "PIE_CHART", "prompt": "Describe a fictional chart showing library visits in River Town.", "minimum_recommended_words": 150},
        {"task_number": 2, "task_type": "OPINION", "prompt": "Discuss whether an imagined town should add more boat routes.", "minimum_recommended_words": 250}
      ]
    }
  ]
}
```
