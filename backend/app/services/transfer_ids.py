"""Source-to-import identity mapping, independent of database and file I/O."""

import uuid

from app.schemas.transfer import ManifestAsset, ManifestCover, PortableTest


def build_id_maps(
    tests: list[PortableTest],
    assets: list[ManifestAsset],
    covers: tuple[ManifestCover, ...] | list[ManifestCover] = (),
) -> dict[str, dict[uuid.UUID, uuid.UUID]]:
    values: dict[str, list[uuid.UUID]] = {
        "tests": [item.id for item in tests],
        "versions": [version.id for item in tests for version in item.versions],
        "modules": [
            module.id for item in tests for version in item.versions for module in version.modules
        ],
        "passages": [
            passage.id
            for item in tests
            for version in item.versions
            for module in version.modules
            for passage in module.passages
        ],
        "parts": [
            part.id
            for item in tests
            for version in item.versions
            for module in version.modules
            for part in module.listening_parts
        ],
        "tasks": [
            task.id
            for item in tests
            for version in item.versions
            for module in version.modules
            for task in module.writing_tasks
        ],
        "speaking_parts": [
            part.id
            for item in tests
            for version in item.versions
            for module in version.modules
            for part in module.speaking_parts
        ],
        "speaking_prompts": [
            prompt.id
            for item in tests
            for version in item.versions
            for module in version.modules
            for part in module.speaking_parts
            for prompt in part.prompts
        ],
        "groups": [
            group.id
            for item in tests
            for version in item.versions
            for module in version.modules
            for group in module.question_groups
        ],
        "questions": [
            question.id
            for item in tests
            for version in item.versions
            for module in version.modules
            for group in module.question_groups
            for question in group.questions
        ],
        "assets": [asset.source_id for asset in assets],
        "covers": [cover.source_id for cover in covers],
    }
    return {kind: {source: uuid.uuid4() for source in ids} for kind, ids in values.items()}
