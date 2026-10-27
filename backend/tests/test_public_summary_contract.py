"""Public catalog optimization must reuse the existing key-free summary contract."""

from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tests import TestRepository as CatalogRepository
from app.schemas.tests import VersionDetail


def test_existing_public_version_summary_excludes_exam_keys_and_response_content():
    schema = VersionDetail.model_json_schema()
    definitions = [schema, *schema.get("$defs", {}).values()]
    fields = {field for definition in definitions for field in definition.get("properties", {})}
    assert not fields.intersection(
        {"answer_key", "answers", "is_correct", "explanation", "blocks", "config", "content"}
    )
    assert {"modules", "question_count", "reading_passages", "listening_sections"} <= fields


async def test_catalog_detail_loading_bounds_each_database_batch():
    session = AsyncMock(spec=AsyncSession)
    session.scalars.return_value = []
    ids = [uuid4() for _ in range(250)]
    assert await CatalogRepository(session).get_versions(ids) == []
    batches = [call.args[0].compile().params["id_1"] for call in session.scalars.call_args_list]
    assert [len(batch) for batch in batches] == [100, 100, 50]
    assert [item for batch in batches for item in batch] == ids
