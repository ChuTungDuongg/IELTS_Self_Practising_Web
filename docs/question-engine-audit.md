# Question engine and attempt presentation audit

Baseline: `4724167200f66e9fcd5a9c5605cd14dfd4e1cfc5` (`main`, 2026-10-26), including the preceding concurrency fixes. The supplied older reference was `43fdc9d`. Next.js → FastAPI → PostgreSQL boundaries remain authoritative.

## Read-only usage evidence

The configured local PostgreSQL database was accessible. All inspection used `SET TRANSACTION READ ONLY`, a statement timeout, and aggregate queries; no content, account data, answer text or credentials are included here. Group counts join `question_groups → test_modules → test_versions → tests`. Published/draft columns exclude archived parent tests; archived includes archived versions or archived parent tests. Historical references list distinct attempts referencing a version/module containing that type, followed by saved answer rows joined through `questions`. These are local observations, not global deployment/backup/export coverage.

Both canonical registries contain **21 types**. Fifteen occur locally; six do not. Every type remains a schema-version-1 transfer contract. Local absence does not prove a type is obsolete. `unknown` applies to usage in other deployments and saved ZIP files for every row.

| Question type | Published | Draft | Archived | Historical references (attempts / answers) | Import compatibility | Proposed action |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| multiple_choice | 6 | 2 | 23 | 2 / 0 | v1 retained | Keep |
| multiple_choice_multiple | 6 | 0 | 36 | 0 / 0 | v1 retained; composite slots | Keep |
| true_false_not_given | 5 | 2 | 30 | 2 / 0 | v1 retained | Keep |
| yes_no_not_given | 1 | 0 | 6 | 0 / 0 | v1 retained | Keep |
| text_completion | 5 | 3 | 18 | 2 / 0 | v1 retained; stable gap IDs | Keep |
| matching_headings | 1 | 0 | 6 | 0 / 0 | v1 retained; legacy heading aliases | Keep; shared option-select implementation |
| matching | 4 | 2 | 17 | 0 / 0 | v1 retained; legacy labels normalized | Keep; shared option-select implementation |
| matching_information | 2 | 1 | 11 | 2 / 0 | v1 retained; paragraph IDs | Keep distinct paragraph semantics |
| matching_features | 0 | 0 | 0 | 0 / 0 | v1 retained; regression fixtures | Keep; shared matching renderer |
| matching_sentence_endings | 1 | 1 | 0 | 2 / 0 | v1 retained | Keep; shared matching renderer |
| summary_completion_word_list | 1 | 0 | 6 | 0 / 0 | v1 retained; option IDs, not text | Keep; shared option-select implementation |
| plan_labelling | 1 | 0 | 6 | 0 / 0 | v1 retained; image and marker references | Keep |
| map_labelling | 1 | 0 | 6 | 2 / 0 | v1 retained; Reading markers / Listening options | Keep |
| diagram_labelling | 2 | 0 | 17 | 0 / 0 | v1 retained; geometry and text answers | Keep distinct diagram semantics |
| form_completion | 0 | 0 | 0 | 0 / 0 | v1 retained; existing ZIP fixtures | Keep structured layout |
| note_completion | 7 | 2 | 29 | 4 / 0 | v1 retained; modern blocks and legacy nodes | Keep |
| table_completion | 2 | 1 | 11 | 0 / 0 | v1 retained; modern segments and legacy cells | Keep |
| flow_chart_completion | 0 | 0 | 0 | 0 / 0 | v1 retained; structured node contract | Keep |
| summary_completion | 0 | 0 | 0 | 0 / 0 | v1 retained; structured node contract | Keep |
| sentence_completion | 0 | 0 | 0 | 0 / 0 | v1 retained; structured node contract | Keep |
| short_answer | 0 | 0 | 0 | 0 / 0 | v1 retained; text response contract | Keep |

Reading locally uses diagram labelling, headings/information/sentence-ending matching, agreement, text/note/table completion, word lists and both MCQ forms. Listening uses map/plan, matching, text/note/table completion and both MCQ forms. No saved `attempt_answers` rows were present in this local snapshot; version-level attempt dependencies still exist as listed. No zero is inferred for inaccessible deployments.

## Compatibility classification and safe consolidation

- **Actively used:** the 15 nonzero types keep canonical IDs, configuration, keys, responses, numbering, renderers and scoring.
- **Shared implementations:** agreement already shares a renderer; matching/features/endings share a renderer/editor; plan/map share a renderer; structured completion and text evaluation already share implementations. Further broad family consolidation would add risk without demonstrated benefit.
- **Small proven duplication:** matching, heading matching and word-list completion repeat the same UUID-valued option select. Share that control only, preserving exact option labels, placeholders, classes, disabled state and callback payloads. Paragraph matching keeps its distinct block-ID choices.
- **Locally unused:** matching_features, form_completion, flow_chart_completion, summary_completion, sentence_completion and short_answer remain supported and offered. They are legitimate IELTS authoring shapes and/or existing transfer fixtures; local absence alone does not establish unnecessary authoring. **No types hidden, deprecated or removed.**
- **Proven obsolete:** none. No schema migration, persisted question conversion, renumbering or data update is justified.

Baseline protection adds one shared fictional JSON contract for every type, consumed by frontend rendering/interaction/serialization/numbering tests and backend validation/normalization/scoring tests. UUIDs, key kinds, response values, multi-slot behavior and immutable fixture input are asserted. Existing legacy normalization, Builder, rich note/table/diagram and transfer suites remain. The v1 ZIP protocol identifier and ID-remapping rules are unchanged.

Baseline before engine changes: **76 backend tests passed** (registry contracts, registry/evaluation, transfer); **69 frontend tests passed** (shared saved contracts, registry and numbering).

## Presentation design and verification

Implementation and final validation results are recorded below as each ordered stage completes. Practice is a UI preference separate from scope, timer, attempt context and Speaking mode. Full Mock must always resolve to Exam. Existing attempts without a preference fall back to Exam; new standalone Reading/Listening starts default to Practice. Neither preference nor styling can override server audio, deadline, authorization or scoring rules.
