from __future__ import annotations

import hashlib
import re
import stat
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domains.questions.normalization import (
    normalize_passage_blocks,
    normalize_question_group_payload,
    remap_question_references,
)
from app.domains.questions.registry import question_registry
from app.models import (
    Asset,
    ListeningPart,
    Question,
    QuestionGroup,
    ReadingPassage,
    Test,
    TestModule,
    TestVersion,
    WritingTask,
)
from app.models.enums import AssetType, ModuleType
from app.repositories.tests import version_detail_query
from app.schemas.transfer import (
    TRANSFER_FORMAT,
    TRANSFER_SCHEMA_VERSION,
    ImportedTest,
    ManifestAsset,
    ManifestTest,
    PortableListeningPart,
    PortableModule,
    PortablePassage,
    PortableQuestion,
    PortableQuestionGroup,
    PortableTest,
    PortableVersion,
    PortableWritingTask,
    TransferImportResult,
    TransferManifest,
)
from app.services.tests import TestService
from app.storage import LocalAssetStorage


@dataclass(slots=True)
class ValidatedPackage:
    manifest: TransferManifest
    tests: list[PortableTest]
    staged_assets: dict[uuid.UUID, Path]


class TransferService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.storage = LocalAssetStorage(settings.resolved_storage_root)

    async def export(self, test_ids: list[uuid.UUID], destination: Path) -> None:
        tests: list[Test] = []
        for test_id in test_ids:
            test = await self.session.scalar(
                select(Test).where(Test.id == test_id).options(selectinload(Test.versions))
            )
            if test is None:
                raise AppError("TRANSFER_TEST_NOT_FOUND", "A selected test does not exist.", 404)
            tests.append(test)

        manifest_tests: list[ManifestTest] = []
        manifest_assets: list[ManifestAsset] = []
        packaged_asset_ids: set[uuid.UUID] = set()
        with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            for test in tests:
                versions = [
                    await self.session.scalar(
                        version_detail_query().where(TestVersion.id == summary.id)
                    )
                    for summary in test.versions
                ]
                portable = self._portable_test(test, [version for version in versions if version])
                test_path = f"tests/{test.id}.json"
                archive.writestr(test_path, portable.model_dump_json(indent=2).encode("utf-8"))
                manifest_tests.append(
                    ManifestTest(source_id=test.id, path=test_path, title=test.title)
                )

                for version in versions:
                    if version is None:
                        continue
                    for asset in self._referenced_assets(version):
                        if asset.id in packaged_asset_ids:
                            continue
                        source = self.storage.resolve(asset.relative_path)
                        digest = self._sha256(source)
                        extension = LocalAssetStorage.IMAGE_TYPES.get(
                            asset.mime_type
                        ) or LocalAssetStorage.AUDIO_TYPES.get(asset.mime_type)
                        if extension is None:
                            raise AppError(
                                "TRANSFER_ASSET_INVALID",
                                "A referenced asset has an unsupported MIME type.",
                                422,
                            )
                        package_path = f"assets/{digest}-{asset.id.hex}{extension}"
                        archive.write(source, package_path)
                        manifest_assets.append(
                            ManifestAsset(
                                source_id=asset.id,
                                source_version_id=asset.test_version_id,
                                path=package_path,
                                asset_type=asset.asset_type,
                                mime_type=asset.mime_type,
                                original_filename=asset.original_name,
                                size=source.stat().st_size,
                                sha256=digest,
                            )
                        )
                        packaged_asset_ids.add(asset.id)

            manifest = TransferManifest(
                exported_at=datetime.now(UTC), tests=manifest_tests, assets=manifest_assets
            )
            archive.writestr("manifest.json", manifest.model_dump_json(indent=2).encode("utf-8"))

    def validate_archive(self, archive_path: Path, staging_root: Path) -> ValidatedPackage:
        try:
            archive = zipfile.ZipFile(archive_path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise self._invalid("The uploaded file is not a valid ZIP package.") from exc
        with archive:
            members = archive.infolist()
            if len(members) > self.settings.max_transfer_files:
                raise self._invalid("The package contains too many files.")
            if (
                sum(member.file_size for member in members)
                > self.settings.max_transfer_uncompressed_mb * 1024 * 1024
            ):
                raise self._invalid("The package exceeds the uncompressed size limit.")
            names: set[str] = set()
            folded_names: set[str] = set()
            for member in members:
                self._validate_member(member)
                folded = member.filename.casefold()
                if member.filename in names or folded in folded_names:
                    raise self._invalid("The package contains duplicate paths.")
                names.add(member.filename)
                folded_names.add(folded)
            if "manifest.json" not in names:
                raise self._invalid("The package does not contain manifest.json.")
            try:
                manifest = TransferManifest.model_validate_json(archive.read("manifest.json"))
            except (KeyError, ValidationError, ValueError) as exc:
                raise self._invalid("The transfer manifest is malformed or unsupported.") from exc
            if (
                manifest.format != TRANSFER_FORMAT
                or manifest.schema_version != TRANSFER_SCHEMA_VERSION
            ):
                raise self._invalid("The transfer package format or schema version is unsupported.")

            expected = (
                {"manifest.json"}
                | {item.path for item in manifest.tests}
                | {item.path for item in manifest.assets}
            )
            if names != expected:
                raise self._invalid("The package contains missing or unexpected files.")
            if len({item.path.casefold() for item in manifest.tests}) != len(manifest.tests):
                raise self._invalid("The manifest contains duplicate test paths.")
            if len({item.source_id for item in manifest.assets}) != len(manifest.assets):
                raise self._invalid("The manifest contains duplicate asset identifiers.")

            portable_tests: list[PortableTest] = []
            for entry in manifest.tests:
                try:
                    payload = PortableTest.model_validate_json(archive.read(entry.path))
                except (KeyError, ValidationError, ValueError) as exc:
                    raise self._invalid(f"Test data at {entry.path} is malformed.") from exc
                if payload.id != entry.source_id:
                    raise self._invalid("A test manifest identifier does not match its test data.")
                portable_tests.append(payload)
            if len({item.id for item in portable_tests}) != len(portable_tests):
                raise self._invalid("The package repeats a source test identifier.")

            version_ids = {version.id for test in portable_tests for version in test.versions}
            asset_metadata = {asset.source_id: asset for asset in manifest.assets}
            if any(asset.source_version_id not in version_ids for asset in manifest.assets):
                raise self._invalid("An asset references an unknown test version.")
            self._validate_graph(portable_tests, asset_metadata)

            staged_assets: dict[uuid.UUID, Path] = {}
            for index, metadata in enumerate(manifest.assets):
                staged = staging_root / f"asset-{index}"
                digest = hashlib.sha256()
                size = 0
                try:
                    with archive.open(metadata.path) as source, staged.open("xb") as target:
                        while chunk := source.read(1024 * 1024):
                            size += len(chunk)
                            digest.update(chunk)
                            target.write(chunk)
                except (KeyError, OSError, RuntimeError) as exc:
                    raise self._invalid(f"Asset {metadata.path} could not be read.") from exc
                if size != metadata.size or digest.hexdigest() != metadata.sha256:
                    raise self._invalid(
                        f"Asset {metadata.path} failed its size or checksum validation."
                    )
                self._validate_asset(metadata, staged)
                staged_assets[metadata.source_id] = staged
            package = ValidatedPackage(
                manifest=manifest, tests=portable_tests, staged_assets=staged_assets
            )
            self._validate_portable_structure(package)
            return package

    async def import_package(self, package: ValidatedPackage) -> TransferImportResult:
        maps = self._build_id_maps(package)
        created_paths: list[str] = []
        imported: list[ImportedTest] = []
        version_count = 0
        try:
            async with self.session.begin():
                for portable_test in package.tests:
                    test = Test(
                        id=maps["tests"][portable_test.id],
                        title=portable_test.title,
                        description=portable_test.description,
                        source_label=portable_test.source_label,
                        test_number=portable_test.test_number,
                        archived_at=portable_test.archived_at,
                    )
                    self.session.add(test)
                    imported.append(ImportedTest(test_id=test.id, title=test.title))
                    versions: dict[uuid.UUID, TestVersion] = {}
                    for portable_version in portable_test.versions:
                        version = TestVersion(
                            id=maps["versions"][portable_version.id],
                            version_number=portable_version.version_number,
                            status=portable_version.status,
                            published_at=portable_version.published_at,
                        )
                        test.versions.append(version)
                        versions[portable_version.id] = version
                        version_count += 1
                    assets: dict[uuid.UUID, Asset] = {}
                    for metadata in package.manifest.assets:
                        owner = versions.get(metadata.source_version_id)
                        if owner is None:
                            continue
                        category = (
                            "audio"
                            if metadata.asset_type == AssetType.LISTENING_AUDIO
                            else "images"
                        )
                        maximum = (
                            (
                                self.settings.max_audio_upload_mb
                                if category == "audio"
                                else self.settings.max_image_upload_mb
                            )
                            * 1024
                            * 1024
                        )
                        stored = self.storage.store_file(
                            category=category,
                            mime_type=metadata.mime_type,
                            original_name=metadata.original_filename,
                            source=package.staged_assets[metadata.source_id],
                            max_bytes=maximum,
                        )
                        created_paths.append(stored.relative_path)
                        asset = Asset(
                            id=maps["assets"][metadata.source_id],
                            asset_type=metadata.asset_type,
                            relative_path=stored.relative_path,
                            mime_type=metadata.mime_type,
                            original_name=metadata.original_filename,
                            file_size=stored.size,
                        )
                        owner.assets.append(asset)
                        assets[metadata.source_id] = asset
                    for portable_version in portable_test.versions:
                        version = versions[portable_version.id]
                        self._build_version(portable_version, version, assets, maps)
                        self._validate_built_version(version)
                await self.session.flush()
        except Exception:
            for relative_path in created_paths:
                self.storage.delete(relative_path)
            raise
        return TransferImportResult(
            imported_tests=imported,
            version_count=version_count,
            asset_count=len(package.manifest.assets),
        )

    @staticmethod
    def _portable_test(test: Test, versions: list[TestVersion]) -> PortableTest:
        return PortableTest(
            id=test.id,
            title=test.title,
            description=test.description,
            source_label=test.source_label,
            test_number=test.test_number,
            archived_at=test.archived_at,
            versions=[TransferService._portable_version(version) for version in versions],
        )

    @staticmethod
    def _portable_version(version: TestVersion) -> PortableVersion:
        return PortableVersion(
            id=version.id,
            version_number=version.version_number,
            status=version.status,
            published_at=version.published_at,
            modules=[
                PortableModule(
                    id=module.id,
                    module_type=module.module_type,
                    title=module.title,
                    recommended_duration_seconds=module.recommended_duration_seconds,
                    order_index=module.order_index,
                    audio_asset_id=module.audio_asset_id,
                    passages=[
                        PortablePassage.model_validate(item, from_attributes=True)
                        for item in module.passages
                    ],
                    listening_parts=[
                        PortableListeningPart.model_validate(item, from_attributes=True)
                        for item in module.listening_parts
                    ],
                    writing_tasks=[
                        PortableWritingTask.model_validate(item, from_attributes=True)
                        for item in module.writing_tasks
                    ],
                    question_groups=[
                        PortableQuestionGroup(
                            id=group.id,
                            passage_id=group.passage_id,
                            listening_part_id=group.listening_part_id,
                            image_asset_id=group.image_asset_id,
                            section_reference=group.section_reference,
                            question_type=group.question_type,
                            instruction=group.instruction,
                            config=group.config,
                            order_index=group.order_index,
                            questions=[
                                PortableQuestion.model_validate(item, from_attributes=True)
                                for item in group.questions
                            ],
                        )
                        for group in module.question_groups
                    ],
                )
                for module in version.modules
            ],
        )

    @staticmethod
    def _referenced_assets(version: TestVersion) -> list[Asset]:
        referenced: dict[uuid.UUID, Asset] = {}
        for module in version.modules:
            if module.audio_asset:
                referenced[module.audio_asset.id] = module.audio_asset
            for task in module.writing_tasks:
                if task.image_asset:
                    referenced[task.image_asset.id] = task.image_asset
            for group in module.question_groups:
                if group.image_asset:
                    referenced[group.image_asset.id] = group.image_asset
        return list(referenced.values())

    @staticmethod
    def _validate_member(member: zipfile.ZipInfo) -> None:
        name = member.filename
        path = PurePosixPath(name)
        mode = member.external_attr >> 16
        if (
            member.is_dir()
            or not name
            or "\\" in name
            or name.startswith("/")
            or re.match(r"^[A-Za-z]:", name)
            or any(part in {"", ".", ".."} for part in path.parts)
            or stat.S_IFMT(mode) == stat.S_IFLNK
        ):
            raise TransferService._invalid("The ZIP contains an unsafe member path.")
        allowed = name == "manifest.json" or (
            len(path.parts) == 2 and path.parts[0] in {"tests", "assets"}
        )
        if not allowed:
            raise TransferService._invalid("The ZIP contains an unexpected file path.")

    @staticmethod
    def _validate_graph(
        tests: list[PortableTest], asset_metadata: dict[uuid.UUID, ManifestAsset]
    ) -> None:
        seen: dict[str, set[uuid.UUID]] = {
            key: set()
            for key in ("versions", "modules", "passages", "parts", "tasks", "groups", "questions")
        }
        referenced_assets: set[uuid.UUID] = set()
        for test in tests:
            test_version_ids = {version.id for version in test.versions}
            asset_types = {
                asset_id: metadata.asset_type
                for asset_id, metadata in asset_metadata.items()
                if metadata.source_version_id in test_version_ids
            }
            for version in test.versions:
                TransferService._remember(seen["versions"], version.id, "version")
                for module in version.modules:
                    TransferService._remember(seen["modules"], module.id, "module")
                    if module.module_type == ModuleType.READING and (
                        module.listening_parts or module.writing_tasks
                    ):
                        raise TransferService._invalid(
                            "A Reading module contains content from another module type."
                        )
                    if module.module_type == ModuleType.LISTENING and (
                        module.passages or module.writing_tasks
                    ):
                        raise TransferService._invalid(
                            "A Listening module contains content from another module type."
                        )
                    if module.module_type == ModuleType.WRITING and (
                        module.passages or module.listening_parts or module.question_groups
                    ):
                        raise TransferService._invalid(
                            "A Writing module contains objective-test content."
                        )
                    passage_ids = {item.id for item in module.passages}
                    part_ids = {item.id for item in module.listening_parts}
                    for item in module.passages:
                        TransferService._remember(seen["passages"], item.id, "passage")
                    for item in module.listening_parts:
                        TransferService._remember(seen["parts"], item.id, "Listening part")
                    for item in module.writing_tasks:
                        TransferService._remember(seen["tasks"], item.id, "Writing task")
                        if (
                            item.image_asset_id
                            and asset_types.get(item.image_asset_id) != AssetType.WRITING_TASK_IMAGE
                        ):
                            raise TransferService._invalid(
                                "A Writing task references a missing or invalid image asset."
                            )
                        if item.image_asset_id:
                            referenced_assets.add(item.image_asset_id)
                    if (
                        module.audio_asset_id
                        and asset_types.get(module.audio_asset_id) != AssetType.LISTENING_AUDIO
                    ):
                        raise TransferService._invalid(
                            "A Listening module references a missing or invalid audio asset."
                        )
                    if module.audio_asset_id:
                        referenced_assets.add(module.audio_asset_id)
                    for group in module.question_groups:
                        TransferService._remember(seen["groups"], group.id, "question group")
                        if group.passage_id and group.passage_id not in passage_ids:
                            raise TransferService._invalid(
                                "A question group references an unknown passage."
                            )
                        if group.listening_part_id and group.listening_part_id not in part_ids:
                            raise TransferService._invalid(
                                "A question group references an unknown Listening part."
                            )
                        if module.module_type == ModuleType.READING and (
                            group.passage_id is None or group.listening_part_id is not None
                        ):
                            raise TransferService._invalid(
                                "A Reading question group has invalid ownership."
                            )
                        if module.module_type == ModuleType.LISTENING and (
                            group.listening_part_id is None or group.passage_id is not None
                        ):
                            raise TransferService._invalid(
                                "A Listening question group has invalid ownership."
                            )
                        if (
                            group.image_asset_id
                            and asset_types.get(group.image_asset_id) != AssetType.QUESTION_IMAGE
                        ):
                            raise TransferService._invalid(
                                "A question group references a missing or invalid image asset."
                            )
                        if group.image_asset_id:
                            referenced_assets.add(group.image_asset_id)
                        for question in group.questions:
                            TransferService._remember(seen["questions"], question.id, "question")
                    question_numbers = [
                        question.number
                        for group in sorted(
                            module.question_groups, key=lambda item: item.order_index
                        )
                        for question in sorted(group.questions, key=lambda item: item.order_index)
                    ]
                    if question_numbers != list(range(1, len(question_numbers) + 1)):
                        raise TransferService._invalid(
                            "Question numbers must form a canonical sequence within each module."
                        )
        if referenced_assets != set(asset_metadata):
            raise TransferService._invalid(
                "The manifest contains an unreferenced or missing asset."
            )

    @staticmethod
    def _remember(values: set[uuid.UUID], value: uuid.UUID, label: str) -> None:
        if value in values:
            raise TransferService._invalid(f"The package repeats a source {label} identifier.")
        values.add(value)

    def _validate_asset(self, metadata: ManifestAsset, source: Path) -> None:
        category = "audio" if metadata.asset_type == AssetType.LISTENING_AUDIO else "images"
        allowed = (
            LocalAssetStorage.AUDIO_TYPES if category == "audio" else LocalAssetStorage.IMAGE_TYPES
        )
        extension = allowed.get(metadata.mime_type)
        original_extension = Path(metadata.original_filename).suffix.lower()
        compatible = {extension} if extension != ".jpg" else {".jpg", ".jpeg"}
        package_extension = Path(metadata.path).suffix.lower()
        if (
            extension is None
            or original_extension not in compatible
            or package_extension != extension
        ):
            raise self._invalid(f"Asset {metadata.path} has an invalid MIME type or filename.")
        with source.open("rb") as input_file:
            head = input_file.read(16)
        signatures = {
            "image/png": head.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": head.startswith(b"\xff\xd8\xff"),
            "image/webp": head.startswith(b"RIFF") and head[8:12] == b"WEBP",
            "audio/mpeg": head.startswith(b"ID3")
            or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0),
            "audio/mp4": head[4:8] == b"ftyp",
            "audio/x-m4a": head[4:8] == b"ftyp",
            "audio/aac": len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0,
            "audio/wav": head.startswith(b"RIFF") and head[8:12] == b"WAVE",
            "audio/x-wav": head.startswith(b"RIFF") and head[8:12] == b"WAVE",
            "audio/ogg": head.startswith(b"OggS"),
        }
        if not signatures.get(metadata.mime_type, False):
            raise self._invalid(
                f"Asset {metadata.path} content does not match its declared MIME type."
            )

    @staticmethod
    def _build_id_maps(package: ValidatedPackage) -> dict[str, dict[uuid.UUID, uuid.UUID]]:
        values: dict[str, list[uuid.UUID]] = {
            "tests": [item.id for item in package.tests],
            "versions": [version.id for item in package.tests for version in item.versions],
            "modules": [
                module.id
                for item in package.tests
                for version in item.versions
                for module in version.modules
            ],
            "passages": [
                passage.id
                for item in package.tests
                for version in item.versions
                for module in version.modules
                for passage in module.passages
            ],
            "parts": [
                part.id
                for item in package.tests
                for version in item.versions
                for module in version.modules
                for part in module.listening_parts
            ],
            "tasks": [
                task.id
                for item in package.tests
                for version in item.versions
                for module in version.modules
                for task in module.writing_tasks
            ],
            "groups": [
                group.id
                for item in package.tests
                for version in item.versions
                for module in version.modules
                for group in module.question_groups
            ],
            "questions": [
                question.id
                for item in package.tests
                for version in item.versions
                for module in version.modules
                for group in module.question_groups
                for question in group.questions
            ],
            "assets": [asset.source_id for asset in package.manifest.assets],
        }
        return {kind: {source: uuid.uuid4() for source in ids} for kind, ids in values.items()}

    @staticmethod
    def _validate_portable_structure(package: ValidatedPackage) -> None:
        maps = TransferService._build_id_maps(package)
        assets = {
            metadata.source_id: Asset(
                id=maps["assets"][metadata.source_id],
                asset_type=metadata.asset_type,
                relative_path=f"validated/{metadata.source_id}",
                mime_type=metadata.mime_type,
                original_name=metadata.original_filename,
                file_size=metadata.size,
            )
            for metadata in package.manifest.assets
        }
        for portable_test in package.tests:
            for portable_version in portable_test.versions:
                version = TestVersion(
                    id=maps["versions"][portable_version.id],
                    version_number=portable_version.version_number,
                    status=portable_version.status,
                    published_at=portable_version.published_at,
                )
                TransferService._build_version(portable_version, version, assets, maps)
                TransferService._validate_built_version(version)

    @staticmethod
    def _build_version(
        source: PortableVersion,
        target: TestVersion,
        assets: dict[uuid.UUID, Asset],
        maps: dict[str, dict[uuid.UUID, uuid.UUID]],
    ) -> None:
        question_map = {str(old): str(new) for old, new in maps["questions"].items()}
        for source_module in source.modules:
            module = TestModule(
                id=maps["modules"][source_module.id],
                module_type=source_module.module_type,
                title=source_module.title,
                recommended_duration_seconds=source_module.recommended_duration_seconds,
                order_index=source_module.order_index,
                audio_asset=assets.get(source_module.audio_asset_id),
            )
            target.modules.append(module)
            passages: dict[uuid.UUID, ReadingPassage] = {}
            parts: dict[uuid.UUID, ListeningPart] = {}
            for item in source_module.passages:
                passage = ReadingPassage(
                    id=maps["passages"][item.id],
                    title=item.title,
                    order_index=item.order_index,
                    content_json=item.content_json,
                    plain_text=item.plain_text,
                )
                module.passages.append(passage)
                passages[item.id] = passage
            for item in source_module.listening_parts:
                part = ListeningPart(
                    id=maps["parts"][item.id], title=item.title, order_index=item.order_index
                )
                module.listening_parts.append(part)
                parts[item.id] = part
            for item in source_module.writing_tasks:
                module.writing_tasks.append(
                    WritingTask(
                        id=maps["tasks"][item.id],
                        task_number=item.task_number,
                        prompt=item.prompt,
                        image_asset=assets.get(item.image_asset_id),
                        minimum_recommended_words=item.minimum_recommended_words,
                        recommended_duration_seconds=item.recommended_duration_seconds,
                        order_index=item.order_index,
                    )
                )
            for item in source_module.question_groups:
                group = QuestionGroup(
                    id=maps["groups"][item.id],
                    passage=passages.get(item.passage_id),
                    listening_part=parts.get(item.listening_part_id),
                    image_asset=assets.get(item.image_asset_id),
                    section_reference=item.section_reference,
                    question_type=item.question_type,
                    instruction=item.instruction,
                    config=remap_question_references(item.config, question_map),
                    order_index=item.order_index,
                )
                module.question_groups.append(group)
                for source_question in item.questions:
                    group.questions.append(
                        Question(
                            id=maps["questions"][source_question.id],
                            number=source_question.number,
                            prompt=source_question.prompt,
                            config=remap_question_references(source_question.config, question_map),
                            answer_key=remap_question_references(
                                source_question.answer_key, question_map
                            ),
                            explanation=source_question.explanation,
                            order_index=source_question.order_index,
                        )
                    )

    @staticmethod
    def _validate_built_version(version: TestVersion) -> None:
        for module in version.modules:
            blocks_by_passage = {
                passage.id: normalize_passage_blocks(passage.content_json, passage.id)
                for passage in module.passages
            }
            for group in module.question_groups:
                passage_id = group.passage.id if group.passage is not None else group.passage_id
                rows = [
                    {
                        "id": question.id,
                        "number": question.number,
                        "prompt": question.prompt,
                        "config": question.config,
                        "answer_key": question.answer_key,
                        "explanation": question.explanation,
                        "order_index": question.order_index,
                    }
                    for question in group.questions
                ]
                try:
                    config, questions = normalize_question_group_payload(
                        question_type=group.question_type,
                        group_config=group.config,
                        questions=rows,
                        group_id=group.id,
                        passage_blocks=blocks_by_passage.get(passage_id, []),
                    )
                    for question, normalized in zip(group.questions, questions, strict=True):
                        question_registry.validate(
                            group.question_type,
                            config,
                            normalized["config"],
                            normalized["answer_key"],
                        )
                        TestService._validate_references(
                            group,
                            question,
                            group_config=config,
                            question_config=normalized["config"],
                            answer_key=normalized["answer_key"],
                            passage_blocks=blocks_by_passage.get(passage_id, []),
                        )
                    TestService._validate_group_references(group, config, questions)
                    group.config = config
                    for question, normalized in zip(group.questions, questions, strict=True):
                        question.config = normalized["config"]
                        question.answer_key = normalized["answer_key"]
                except (KeyError, TypeError, ValueError, ValidationError) as exc:
                    raise TransferService._invalid(
                        "An imported question group is structurally invalid."
                    ) from exc

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _invalid(message: str) -> AppError:
        return AppError("TRANSFER_PACKAGE_INVALID", message, 422)
