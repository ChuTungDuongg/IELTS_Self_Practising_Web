# Builder navigation, shared Listening audio, and Reading instructions

## Scope

This change keeps the current Next.js/FastAPI/PostgreSQL architecture and stable section/question identities. It fixes Builder workspace navigation, moves Listening audio ownership from each `ListeningPart` to the Listening `TestModule`, adds `yes_no_not_given`, and centralizes question-group instruction rendering.

## Builder navigation

The canonical edit route remains `/admin/tests/[testId]/versions/[versionId]/edit`. A `workspace` query parameter selects `overview`, `reading`, or `listening`. The server page validates the parameter and renders only that workspace. Navigation uses Next.js `Link`, so selection is URL-backed and survives `router.refresh()`. Writing remains a non-interactive placeholder until a Writing Builder exists.

## Shared Listening audio

`TestModule.audio_asset_id` is nullable and is only used by Listening modules. `ListeningPart.audio_asset_id` is removed after migration validation and backfill. Builder, active-exam, and review DTOs expose one module-level Listening audio asset; individual sections no longer expose audio.

The migration handles legacy data as follows:

- no part audio: module audio remains null;
- one distinct audio across the module: copy it to the module;
- repeated references to the same audio: copy the shared ID once;
- more than one distinct audio: abort with a clear error before dropping the legacy column.

The audio attach endpoint targets the Listening module, verifies draft ownership and asset type/version, and changes only the module foreign key. Replacing or removing it cannot cascade into sections or questions. Candidate and review views mount one player outside section-specific content, so section changes do not remount or restart it.

## YES / NO / NOT GIVEN

`yes_no_not_given` is a distinct registry type in frontend and backend. It uses the single-option answer primitive with canonical values `YES`, `NO`, and `NOT_GIVEN`. Normalization accepts the existing underscore/visible-space convention while persistence and grading use canonical values.

## Instruction architecture

Each frontend question registry definition owns an instruction generator. The generator receives the group plus contextual passage number and returns an intro and optional labelled explanations. The persisted `group.instruction` remains available as a custom override. Generated defaults are not duplicated in the database.

`QuestionGroupInstruction` is the only visual instruction component. Builder Preview, Reading Runner, and Reading Review use it exactly once per group. Passage numbers use the passage's zero-based `order_index + 1`. Completion instructions derive word/number limits from question config; mixed per-question limits fall back to wording that tells candidates to follow each answer's configured limit.

## Compatibility and validation

Published versions remain immutable. Cloning copies the module-level audio reference. Asset-preservation checks include module-level audio. Active exam DTOs continue to exclude answer keys. Existing custom instructions and all stable UUIDs are preserved.

