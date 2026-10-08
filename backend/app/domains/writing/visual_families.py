from enum import StrEnum

from app.domains.writing.task_types import WritingTaskType


class VisualFamily(StrEnum):
    CHART_TABLE = "chart_table"
    PROCESS = "process"
    MAP = "map"
    SYSTEM = "system"
    OTHER = "other"


VISUAL_FAMILIES = {
    WritingTaskType.LINE_GRAPH: VisualFamily.CHART_TABLE,
    WritingTaskType.BAR_CHART: VisualFamily.CHART_TABLE,
    WritingTaskType.PIE_CHART: VisualFamily.CHART_TABLE,
    WritingTaskType.TABLE: VisualFamily.CHART_TABLE,
    WritingTaskType.MIXED_CHARTS: VisualFamily.CHART_TABLE,
    WritingTaskType.PROCESS: VisualFamily.PROCESS,
    WritingTaskType.MAP_PLAN: VisualFamily.MAP,
    WritingTaskType.OBJECT_SYSTEM_DIAGRAM: VisualFamily.SYSTEM,
    WritingTaskType.OTHER_VISUAL: VisualFamily.OTHER,
}


def visual_family(task_type: WritingTaskType) -> VisualFamily:
    return VISUAL_FAMILIES[task_type]
