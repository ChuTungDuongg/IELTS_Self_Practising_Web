from app.domains.questions.numbering import group_slots
from app.models import TestVersion
from app.schemas.tests import (
    ListeningSectionSummary,
    ModuleSummary,
    QuestionGroupSummary,
    ReadingPassageSummary,
    VersionDetail,
    WritingTaskSummary,
)


def group_summary(group) -> QuestionGroupSummary | None:
    slots = group_slots(group.question_type, group.questions)
    if not slots:
        return None
    return QuestionGroupSummary(
        question_type=group.question_type,
        start_number=min(slots),
        end_number=max(slots),
    )


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
                question_count=sum(
                    len(group_slots(group.question_type, group.questions))
                    for group in module.question_groups
                ),
                reading_passages=[
                    ReadingPassageSummary(
                        title=passage.title,
                        order_index=passage.order_index,
                        question_groups=[
                            summary
                            for group in sorted(
                                passage.question_groups, key=lambda item: item.order_index
                            )
                            if (summary := group_summary(group)) is not None
                        ],
                    )
                    for passage in sorted(module.passages, key=lambda item: item.order_index)
                ],
                listening_sections=[
                    ListeningSectionSummary(
                        title=part.title,
                        order_index=part.order_index,
                        question_groups=[
                            summary
                            for group in sorted(
                                part.question_groups, key=lambda item: item.order_index
                            )
                            if (summary := group_summary(group)) is not None
                        ],
                    )
                    for part in sorted(module.listening_parts, key=lambda item: item.order_index)
                ],
                writing_tasks=[
                    WritingTaskSummary(
                        task_number=task.task_number,
                        task_type=task.task_type,
                        prompt_excerpt=(task.prompt.strip()[:140] or None),
                    )
                    for task in sorted(module.writing_tasks, key=lambda item: item.order_index)
                ],
            )
            for module in version.modules
        ],
    )
