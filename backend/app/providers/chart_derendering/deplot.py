"""Backend-only bounded HTTP transport. Transformers lives in its own service."""

import asyncio
import json

import httpx

from app.core.config import Settings
from app.domains.scoring.deplot_parser import DePlotParseError, parse_deplot
from app.providers.chart_derendering import ChartSpecialistFailure
from app.providers.writing_llm.base import ImagePart
from app.schemas.chart_cross_check import SpecialistChartObservation


class DePlotChartDerenderingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def extract(self, image: ImagePart) -> SpecialistChartObservation:
        settings = self.settings
        try:
            url = httpx.URL(settings.ai_writing_deplot_base_url)
        except httpx.InvalidURL:
            raise ChartSpecialistFailure() from None
        if (
            settings.ai_writing_chart_specialist_provider != "deplot"
            or url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.query
            or url.fragment
        ):
            raise ChartSpecialistFailure()
        headers = {"Content-Type": image.mime_type}
        if settings.ai_writing_modal_key and settings.ai_writing_modal_secret:
            headers.update(
                {
                    "Modal-Key": settings.ai_writing_modal_key,
                    "Modal-Secret": settings.ai_writing_modal_secret,
                }
            )
        try:
            async with (
                asyncio.timeout(settings.ai_writing_chart_specialist_timeout_seconds),
                httpx.AsyncClient(
                    timeout=settings.ai_writing_chart_specialist_timeout_seconds,
                    follow_redirects=False,
                ) as client,
            ):
                # One perception request, no retries or foreign redirect credential forwarding.
                async with client.stream(
                    "POST", str(url).rstrip("/") + "/extract", headers=headers, content=image.data
                ) as response:
                    if response.status_code != 200:
                        raise ChartSpecialistFailure()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 32768:
                            raise ChartSpecialistFailure("CHART_SPECIALIST_PARSE_FAILED")
            output = json.loads(data)
            if (
                not isinstance(output, dict)
                or output.get("model") != settings.ai_writing_deplot_model
                or output.get("revision") != settings.ai_writing_deplot_revision
            ):
                raise ChartSpecialistFailure()
            return parse_deplot(output.get("table"))
        except (DePlotParseError, ValueError, UnicodeError):
            raise ChartSpecialistFailure("CHART_SPECIALIST_PARSE_FAILED") from None
        except (httpx.HTTPError, TimeoutError):
            raise ChartSpecialistFailure() from None
