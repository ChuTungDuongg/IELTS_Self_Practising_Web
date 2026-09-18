import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionFactory
from app.models import Question, QuestionGroup, ReadingPassage, Test, TestModule, TestVersion
from app.models.enums import ModuleType, VersionStatus

SEED_TITLE = "Harbour City Renewable Transport — Fictional Practice"


async def seed() -> None:
    async with SessionFactory() as session, session.begin():
        if await session.scalar(select(Test.id).where(Test.title == SEED_TITLE)):
            return
        practice_test = Test(
            title=SEED_TITLE,
            description="Original fictional material for local architecture validation.",
            source_label="Project sample",
            test_number=1,
        )
        version = TestVersion(
            version_number=1,
            status=VersionStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        module = TestModule(
            module_type=ModuleType.READING,
            title="Reading",
            recommended_duration_seconds=3600,
            order_index=0,
        )
        block_id = uuid4()
        passage = ReadingPassage(
            title="Electric Ferries in Harbour City",
            order_index=0,
            content_json=[
                {
                    "id": str(block_id),
                    "type": "paragraph",
                    "text": "Harbour City introduced electric ferries to reduce noise and local emissions.",
                }
            ],
            plain_text="Harbour City introduced electric ferries to reduce noise and local emissions.",
        )
        group = QuestionGroup(
            passage=passage,
            question_type="multiple_choice",
            instruction="Choose the best answer.",
            config={},
            order_index=0,
        )
        group.questions.append(
            Question(
                number=1,
                prompt="Why did Harbour City introduce electric ferries?",
                config={
                    "options": [
                        {"id": "A", "label": "To reduce noise and local emissions"},
                        {"id": "B", "label": "To increase ticket prices"},
                    ]
                },
                answer_key={"type": "single_choice", "accepted": ["A"]},
                explanation="The passage states both reasons directly.",
                order_index=0,
            )
        )
        module.passages.append(passage)
        module.question_groups.append(group)
        version.modules.append(module)
        practice_test.versions.append(version)
        session.add(practice_test)


if __name__ == "__main__":
    asyncio.run(seed())
