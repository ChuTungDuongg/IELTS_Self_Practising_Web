"""Mutable draft Speaking authoring and complete-content validation."""

from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.exceptions import AppError
from app.models import SpeakingPart, SpeakingPrompt, TestModule, User
from app.models.enums import ModuleType, SpeakingPromptType
from app.repositories.speaking import SpeakingRepository
from app.schemas.common import ValidationIssue
from app.schemas.speaking import (
    BuilderSpeakingPart,
    SpeakingPartOrderWrite,
    SpeakingPartUpdate,
    SpeakingPartWrite,
    SpeakingPromptCreate,
    SpeakingPromptOrderWrite,
    SpeakingPromptWrite,
)
from app.services.access_policy import AccessPolicy
from app.services.draft_revisions import advance_revision


def initialize_speaking_parts(module: TestModule) -> None:
    for number in (1, 2, 3):
        part = SpeakingPart(part_number=number, order_index=number - 1)
        if number == 2:
            part.prompts.append(
                SpeakingPrompt(
                    prompt_type=SpeakingPromptType.LONG_TURN,
                    prompt_text="",
                    preparation_seconds=60,
                    response_seconds=120,
                    config_json={},
                    order_index=0,
                )
            )
        module.speaking_parts.append(part)


def legal_prompt_type(part_number: int, prompt_type: SpeakingPromptType) -> bool:
    return prompt_type in (
        {SpeakingPromptType.LONG_TURN, SpeakingPromptType.FOLLOW_UP}
        if part_number == 2
        else {SpeakingPromptType.SHORT_ANSWER}
    )


def validate_speaking_module(module: TestModule) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def issue(path, message):
        issues.append(ValidationIssue(path=f"speaking.{path}", message=message))

    parts = module.speaking_parts
    if sorted(part.part_number for part in parts) != [1, 2, 3]:
        issue("parts", "A complete Speaking module requires exactly one Part 1, 2 and 3.")
    if sorted(part.order_index for part in parts) != list(range(len(parts))):
        issue("parts", "Speaking parts must use canonical contiguous ordering.")
    for part in parts:
        path = f"parts.{part.part_number}"
        prompts = sorted(part.prompts, key=lambda item: item.order_index)
        if not prompts:
            issue(path, "Add required prompts to this part.")
        if [item.order_index for item in prompts] != list(range(len(prompts))):
            issue(path, "Prompts must use canonical contiguous ordering.")
        if part.part_number == 2:
            mains = [item for item in prompts if item.prompt_type == SpeakingPromptType.LONG_TURN]
            if (
                len(mains) != 1
                or not prompts
                or prompts[0].prompt_type != SpeakingPromptType.LONG_TURN
            ):
                issue(path, "Part 2 requires one long turn before optional follow-ups.")
        for prompt in prompts:
            prompt_path = f"{path}.prompts.{prompt.id}"
            if not legal_prompt_type(part.part_number, prompt.prompt_type):
                issue(prompt_path, "This prompt type is not allowed in this part.")
            if not prompt.prompt_text.strip():
                issue(prompt_path, "Prompt text must not be empty.")
            try:
                contract = SpeakingPromptWrite.model_validate(
                    {
                        "prompt_type": prompt.prompt_type,
                        "prompt_text": prompt.prompt_text,
                        "preparation_seconds": prompt.preparation_seconds,
                        "response_seconds": prompt.response_seconds,
                        "config_json": prompt.config_json,
                    }
                )
                if prompt.prompt_type == SpeakingPromptType.LONG_TURN:
                    if prompt.preparation_seconds <= 0:
                        issue(prompt_path, "Long-turn preparation time must be positive.")
                    if any(not point.strip() for point in contract.config_json.cue_points):
                        issue(prompt_path, "Cue points must not be empty.")
                elif contract.config_json.cue_points or prompt.preparation_seconds != 0:
                    issue(prompt_path, "Only long turns may have cue points or preparation time.")
            except ValidationError:
                issue(prompt_path, "Invalid prompt timers or cue-card configuration.")
    return issues


class SpeakingBuilderService:
    def __init__(self, session: AsyncSession, actor: User | None = None):
        self.session = session
        self.policy = AccessPolicy(session, actor)
        self.repository = SpeakingRepository(session)

    async def _module(self, module_id: UUID, *, mutable: bool = True):
        version_id = await self.repository.module_version_id(module_id)
        if version_id is None:
            raise AppError("SPEAKING_MODULE_NOT_FOUND", "The Speaking module does not exist.", 404)
        await self.policy.lock_version(version_id, mutable=mutable, builder=not mutable)
        module = await self.repository.module(module_id, lock=mutable)
        if module is None or module.module_type != ModuleType.SPEAKING:
            raise AppError("SPEAKING_MODULE_NOT_FOUND", "The Speaking module does not exist.", 404)
        return module

    async def _part(self, part_id: UUID):
        module_id = await self.repository.part_module_id(part_id)
        if module_id is None:
            raise AppError("SPEAKING_PART_NOT_FOUND", "The Speaking part does not exist.", 404)
        module = await self._module(module_id)
        part = next(item for item in module.speaking_parts if item.id == part_id)
        set_committed_value(part, "module", module)
        return part

    @staticmethod
    def _check_type(part: SpeakingPart, body: SpeakingPromptWrite):
        if not legal_prompt_type(part.part_number, body.prompt_type):
            raise AppError(
                "SPEAKING_PROMPT_INVALID", "This prompt type is not allowed in this part.", 422
            )

    @staticmethod
    def _apply(prompt: SpeakingPrompt, body: SpeakingPromptWrite):
        prompt.prompt_type = body.prompt_type
        prompt.prompt_text = body.prompt_text
        prompt.preparation_seconds = body.preparation_seconds
        prompt.response_seconds = body.response_seconds
        prompt.config_json = body.config_json.model_dump()

    @staticmethod
    def _normalize(part: SpeakingPart):
        part.prompts.sort(key=lambda item: item.order_index)
        for index, prompt in enumerate(part.prompts):
            prompt.order_index = index

    async def create_part(self, module_id: UUID, body: SpeakingPartWrite) -> BuilderSpeakingPart:
        async with self.session.begin():
            module = await self._module(module_id)
            if any(item.part_number == body.part_number for item in module.speaking_parts):
                raise AppError(
                    "SPEAKING_PART_EXISTS", "This logical Speaking part already exists.", 409
                )
            part = SpeakingPart(
                **body.model_dump(), order_index=len(module.speaking_parts), prompts=[]
            )
            module.speaking_parts.append(part)
            module.revision += 1
            await self.session.flush()
            return BuilderSpeakingPart.model_validate(part)

    async def update_part(self, part_id: UUID, body: SpeakingPartUpdate) -> BuilderSpeakingPart:
        async with self.session.begin():
            part = await self._part(part_id)
            advance_revision(part, body.expected_revision)
            existing = {item.id: item for item in part.prompts}
            retained = []
            for item in sorted(body.prompts, key=lambda prompt: prompt.order_index):
                self._check_type(part, item)
                if item.id is not None and item.id not in existing:
                    raise AppError(
                        "SPEAKING_PROMPT_INVALID", "A prompt does not belong to this part.", 422
                    )
                prompt = existing[item.id] if item.id else SpeakingPrompt(id=uuid4())
                self._apply(prompt, item)
                prompt.order_index = item.order_index
                retained.append(prompt)
            part.title = body.title
            part.instructions = body.instructions
            part.prompts = retained
            await self.session.flush()
            return BuilderSpeakingPart.model_validate(part)

    async def create_prompt(self, part_id: UUID, body: SpeakingPromptCreate) -> BuilderSpeakingPart:
        async with self.session.begin():
            part = await self._part(part_id)
            advance_revision(part, body.expected_revision)
            self._check_type(part, body)
            if len(part.prompts) >= 100:
                raise AppError(
                    "SPEAKING_PROMPT_INVALID", "A part may contain at most 100 prompts.", 422
                )
            prompt = SpeakingPrompt(order_index=len(part.prompts))
            self._apply(prompt, body)
            part.prompts.append(prompt)
            self._normalize(part)
            await self.session.flush()
            return BuilderSpeakingPart.model_validate(part)

    async def reorder_prompts(
        self, part_id: UUID, body: SpeakingPromptOrderWrite
    ) -> BuilderSpeakingPart:
        async with self.session.begin():
            part = await self._part(part_id)
            advance_revision(part, body.expected_revision)
            prompts = {item.id: item for item in part.prompts}
            if set(body.prompt_ids) != set(prompts):
                raise AppError(
                    "SPEAKING_PROMPT_INVALID",
                    "Reorder must include every prompt exactly once.",
                    422,
                )
            part.prompts = [prompts[identifier] for identifier in body.prompt_ids]
            for index, prompt in enumerate(part.prompts):
                prompt.order_index = index
            await self.session.flush()
            return BuilderSpeakingPart.model_validate(part)

    async def update_prompt(
        self, part_id: UUID, prompt_id: UUID, body: SpeakingPromptCreate
    ) -> BuilderSpeakingPart:
        async with self.session.begin():
            part = await self._part(part_id)
            advance_revision(part, body.expected_revision)
            self._check_type(part, body)
            prompt = next((item for item in part.prompts if item.id == prompt_id), None)
            if prompt is None:
                raise AppError(
                    "SPEAKING_PROMPT_NOT_FOUND", "The Speaking prompt does not exist.", 404
                )
            self._apply(prompt, body)
            await self.session.flush()
            return BuilderSpeakingPart.model_validate(part)

    async def delete_prompt(
        self, part_id: UUID, prompt_id: UUID, *, expected_revision: int
    ) -> BuilderSpeakingPart:
        async with self.session.begin():
            part = await self._part(part_id)
            advance_revision(part, expected_revision)
            prompt = next((item for item in part.prompts if item.id == prompt_id), None)
            if prompt is None:
                raise AppError(
                    "SPEAKING_PROMPT_NOT_FOUND", "The Speaking prompt does not exist.", 404
                )
            part.prompts.remove(prompt)
            self._normalize(part)
            await self.session.flush()
            return BuilderSpeakingPart.model_validate(part)

    async def delete_part(self, part_id: UUID, *, expected_revision: int) -> None:
        async with self.session.begin():
            part = await self._part(part_id)
            advance_revision(part, expected_revision)
            module = part.module
            module.speaking_parts.remove(part)
            for index, item in enumerate(
                sorted(module.speaking_parts, key=lambda item: item.order_index)
            ):
                item.order_index = index
            module.revision += 1
            await self.session.flush()

    async def reorder_parts(
        self, module_id: UUID, body: SpeakingPartOrderWrite
    ) -> list[BuilderSpeakingPart]:
        async with self.session.begin():
            module = await self._module(module_id)
            advance_revision(module, body.expected_revision)
            parts = {part.id: part for part in module.speaking_parts}
            if set(body.part_ids) != set(parts):
                raise AppError(
                    "SPEAKING_PART_INVALID", "Reorder must include every part exactly once.", 422
                )
            for index, identifier in enumerate(body.part_ids):
                parts[identifier].order_index = index
            await self.session.flush()
            return [
                BuilderSpeakingPart.model_validate(parts[identifier])
                for identifier in body.part_ids
            ]
