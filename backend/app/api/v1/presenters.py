from app.models import TestVersion
from app.schemas.tests import ModuleSummary, VersionDetail


def present_version(version: TestVersion) -> VersionDetail:
    return VersionDetail(
        id=version.id,
        test_id=version.test_id,
        test_title=version.test.title,
        version_number=version.version_number,
        status=version.status,
        created_at=version.created_at,
        published_at=version.published_at,
        modules=[
            ModuleSummary(
                id=module.id,
                module_type=module.module_type,
                title=module.title,
                recommended_duration_seconds=module.recommended_duration_seconds,
                passage_count=len(module.passages),
                listening_part_count=len(module.listening_parts),
                writing_task_count=len(module.writing_tasks),
                question_count=sum(len(group.questions) for group in module.question_groups),
            )
            for module in version.modules
        ],
    )
