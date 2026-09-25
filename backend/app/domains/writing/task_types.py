from enum import StrEnum


class WritingTaskType(StrEnum):
    LINE_GRAPH = "LINE_GRAPH"
    BAR_CHART = "BAR_CHART"
    PIE_CHART = "PIE_CHART"
    TABLE = "TABLE"
    MIXED_CHARTS = "MIXED_CHARTS"
    PROCESS = "PROCESS"
    MAP_PLAN = "MAP_PLAN"
    OBJECT_SYSTEM_DIAGRAM = "OBJECT_SYSTEM_DIAGRAM"
    OTHER_VISUAL = "OTHER_VISUAL"
    OPINION = "OPINION"
    DISCUSS_BOTH_VIEWS = "DISCUSS_BOTH_VIEWS"
    DISCUSS_BOTH_VIEWS_AND_OPINION = "DISCUSS_BOTH_VIEWS_AND_OPINION"
    ADVANTAGES_DISADVANTAGES = "ADVANTAGES_DISADVANTAGES"
    ADVANTAGES_OUTWEIGH_DISADVANTAGES = "ADVANTAGES_OUTWEIGH_DISADVANTAGES"
    PROBLEM_SOLUTION = "PROBLEM_SOLUTION"
    CAUSE_SOLUTION = "CAUSE_SOLUTION"
    TWO_PART_QUESTION = "TWO_PART_QUESTION"
    OTHER_ESSAY = "OTHER_ESSAY"


TASK_ONE_TYPES = frozenset(
    {
        WritingTaskType.LINE_GRAPH,
        WritingTaskType.BAR_CHART,
        WritingTaskType.PIE_CHART,
        WritingTaskType.TABLE,
        WritingTaskType.MIXED_CHARTS,
        WritingTaskType.PROCESS,
        WritingTaskType.MAP_PLAN,
        WritingTaskType.OBJECT_SYSTEM_DIAGRAM,
        WritingTaskType.OTHER_VISUAL,
    }
)
TASK_TWO_TYPES = frozenset(WritingTaskType) - TASK_ONE_TYPES


def validate_task_type(task_number: int, task_type: WritingTaskType | None) -> None:
    if task_type is None:
        return
    allowed = (
        TASK_ONE_TYPES if task_number == 1 else TASK_TWO_TYPES if task_number == 2 else frozenset()
    )
    if task_type not in allowed:
        raise ValueError(f"{task_type.value} is not valid for Writing Task {task_number}")
