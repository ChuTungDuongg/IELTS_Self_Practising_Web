"""Optional independent chart perception; no language scoring dependency."""

from typing import Protocol

from app.providers.writing_llm.base import ImagePart
from app.schemas.chart_cross_check import SpecialistChartObservation


class ChartSpecialistFailure(Exception):
    def __init__(self, code: str = "CHART_SPECIALIST_UNAVAILABLE") -> None:
        self.code = code
        super().__init__(code)


class ChartDerenderingProvider(Protocol):
    async def extract(self, image: ImagePart) -> SpecialistChartObservation: ...
