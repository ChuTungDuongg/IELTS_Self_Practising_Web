"""Real workers/SSE/services with fake persistence and providers, no database or model."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_task1_visual import Task1FakeProvider
from test_task1_visual import request as task1_request
from test_writing_ai import ESSAY, FakeProvider

from app.api.v1 import writing_ai as routes
from app.core.config import Settings
from app.domains.scoring.mts_prompts import effective_prompt_version
from app.domains.scoring.writing import WritingScoringRequest
from app.models import WritingAIGradingRun
from app.models.enums import WritingAIRunStatus
from app.services import writing_ai, writing_ai_worker
from app.services.task1_input import TASK1_PROMPT_VERSION
from app.services.writing_ai import CANCELLATION_CODE, WritingAIService, input_fingerprint
from app.services.writing_ai_worker import WritingAIWorker


class MemorySession:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    @asynccontextmanager
    async def begin(self):
        async with self.store.lock:
            yield


class MemoryRepository:
    """Replace only DB access; production state transitions and event payloads still run."""

    def __init__(self, session):
        self.store = session.store

    async def run(self, run_id, *, user_id=None, lock=False):
        row = self.store.row
        return row if row.id == run_id and user_id in {None, row.requested_by_user_id} else None

    async def runs(self, attempt_id, task_id, **_kwargs):
        row = self.store.row
        return [row] if (attempt_id, task_id) == (row.attempt_id, row.writing_task_id) else []

    async def events(self, _run_id, after):
        return [event for event in self.store.events if event.sequence > after][:100]

    async def append_event(self, _run, event_type, payload):
        self.store.events.append(
            SimpleNamespace(
                sequence=len(self.store.events) + 1,
                event_type=event_type,
                payload=payload.model_dump(mode="json"),
                created_at=datetime.now(UTC),
            )
        )
        if len((self.store.row.result_json or {}).get("criteria", {})) == 3:
            self.store.partial_ready.set()


class WaitForRelease:
    wait_for_reference = False

    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()
        self.interrupted = asyncio.Event()

    async def complete(self, messages, schema, *, options=None):
        # Task 1 waits in perception; Task 2 waits in one criterion's completion.
        if (self.wait_for_reference and "reference" in schema["properties"]) or (
            not self.wait_for_reference
            and "score" in schema["properties"]
            and "Criterion: Grammatical Range and Accuracy." in messages[0]["content"]
        ):
            self.waiting.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.interrupted.set()
                raise
        return await super().complete(messages, schema, options=options)


class WaitingTask1Provider(WaitForRelease, Task1FakeProvider):
    wait_for_reference = True


class WaitingTask2Provider(WaitForRelease, FakeProvider):
    pass


@pytest.fixture(params=[1, 2])
def lifecycle(request, monkeypatch):
    settings = Settings(
        _env_file=None, ai_writing_enabled=True, ai_writing_vllm_base_url="https://llm.example/v1"
    )
    task_number = request.param
    scoring_request = (
        task1_request()
        if task_number == 1
        else WritingScoringRequest(
            attempt_id=uuid4(),
            writing_task_id=uuid4(),
            prompt="Discuss fictional parks.",
            response=ESSAY,
        )
    )
    version = (
        TASK1_PROMPT_VERSION
        if task_number == 1
        else effective_prompt_version(settings.ai_writing_prompt_version)
    )
    owner = uuid4()
    now = datetime.now(UTC)
    row = WritingAIGradingRun(
        id=uuid4(),
        attempt_id=scoring_request.attempt_id,
        writing_task_id=scoring_request.writing_task_id,
        requested_by_user_id=owner,
        status=WritingAIRunStatus.PENDING,
        provider="vllm",
        model=settings.ai_writing_vllm_model,
        prompt_version=version,
        input_fingerprint=input_fingerprint(
            scoring_request, version, "vllm", settings.ai_writing_vllm_model
        ),
        created_at=now,
        updated_at=now,
    )
    store = SimpleNamespace(row=row, events=[], lock=asyncio.Lock(), partial_ready=asyncio.Event())

    def sessions():
        return MemorySession(store)

    provider = WaitingTask1Provider() if task_number == 1 else WaitingTask2Provider()
    runner = WritingAIWorker(sessions, settings, provider)
    monkeypatch.setattr(writing_ai, "WritingAIRepository", MemoryRepository)
    monkeypatch.setattr(writing_ai_worker, "WritingAIRepository", MemoryRepository)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)

    async def input_request(_self, attempt_id, task_id, **_kwargs):
        assert (attempt_id, task_id) == (row.attempt_id, row.writing_task_id)
        return scoring_request

    monkeypatch.setattr(WritingAIService, "input", input_request)
    api = WritingAIService(sessions(), owner, settings)
    return SimpleNamespace(
        store=store, runner=runner, api=api, provider=provider, owner=owner, sessions=sessions
    )


@pytest.mark.parametrize("disconnect", ["client_disconnect", "request_cancelled"])
async def test_sse_observer_disappearing_keeps_detached_provider_and_run_alive(
    lifecycle, disconnect
):
    run_id = lifecycle.store.row.id
    lifecycle.runner.launch(run_id)
    job = writing_ai_worker._tasks[run_id]
    observer = stream = None
    disconnected = False
    polled = asyncio.Event()

    async def is_disconnected():
        polled.set()
        return disconnected

    try:
        await asyncio.wait_for(lifecycle.provider.waiting.wait(), 2)
        await asyncio.wait_for(lifecycle.store.partial_ready.wait(), 2)
        before = await lifecycle.api.get(run_id)
        stream = routes.event_stream(
            SimpleNamespace(is_disconnected=is_disconnected),
            run_id,
            lifecycle.owner,
            len(lifecycle.store.events),
            lifecycle.runner,
        )
        observer = asyncio.create_task(anext(stream))
        await asyncio.wait_for(polled.wait(), 2)
        if disconnect == "client_disconnect":
            disconnected = True
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(observer, 2)
        else:
            observer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await observer
        assert not job.done() and writing_ai_worker._tasks[run_id] is job
        assert not lifecycle.provider.interrupted.is_set()
        after = await lifecycle.api.get(run_id)
        assert after.status == WritingAIRunStatus.RUNNING and after.error_code is None
        assert after.progress == before.progress and len(after.progress) == 3
        recovered = await lifecycle.api.list(after.attempt_id, after.writing_task_id)
        assert [item.id for item in recovered.items] == [run_id]
        # A repeated launch cannot start a duplicate worker/provider.
        lifecycle.runner.launch(run_id)
        assert writing_ai_worker._tasks[run_id] is job
        lifecycle.provider.release.set()
        await asyncio.wait_for(job, 2)
        saved = await lifecycle.api.get(run_id)
        assert saved.status == WritingAIRunStatus.COMPLETED and len(saved.progress) == 4
        assert saved.result is not None and not lifecycle.provider.interrupted.is_set()
        recovered = await lifecycle.api.list(saved.attempt_id, saved.writing_task_id)
        assert recovered.items[0] == saved
    finally:
        if observer is not None and not observer.done():
            observer.cancel()
            await asyncio.gather(observer, return_exceptions=True)
        if stream is not None:
            await stream.aclose()
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


async def test_process_shutdown_remains_a_legitimate_worker_stop(lifecycle, caplog):
    caplog.set_level("INFO", logger="app.services.writing_ai_worker")
    row = lifecycle.store.row
    lifecycle.runner.launch(row.id)
    job = writing_ai_worker._tasks[row.id]
    try:
        await asyncio.wait_for(lifecycle.provider.waiting.wait(), 2)
        await asyncio.wait_for(lifecycle.store.partial_ready.wait(), 2)
        await writing_ai_worker.stop_writing_ai_workers()
        assert job.cancelled() and lifecycle.provider.interrupted.is_set()
        saved = await lifecycle.api.get(row.id)
        assert saved.status == WritingAIRunStatus.FAILED and saved.error_code == "RUN_INTERRUPTED"
        assert len(saved.progress) == 3
        assert "source=shutdown" in caplog.text and "source=explicit_user" not in caplog.text
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


async def test_explicit_cancel_endpoint_still_interrupts_provider_and_preserves_terminal_state(
    lifecycle, caplog
):
    caplog.set_level("INFO", logger="app.services.writing_ai_worker")
    row = lifecycle.store.row
    lifecycle.runner.launch(row.id)
    job = writing_ai_worker._tasks[row.id]
    try:
        await asyncio.wait_for(lifecycle.provider.waiting.wait(), 2)
        await asyncio.wait_for(lifecycle.store.partial_ready.wait(), 2)
        before = await lifecycle.api.get(row.id)
        stopped = await routes.cancel_run(
            row.id,
            user=SimpleNamespace(id=lifecycle.owner),
            session=lifecycle.sessions(),
            worker=lifecycle.runner,
        )
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(job, 2)
        assert lifecycle.provider.interrupted.is_set()
        assert (
            stopped.status == WritingAIRunStatus.FAILED and stopped.error_code == CANCELLATION_CODE
        )
        assert stopped.progress == before.progress and len(stopped.progress) == 3
        assert await lifecycle.api.get(row.id) == stopped
        assert lifecycle.store.events[-1].event_type == "run.failed"
        assert "source=explicit_user" in caplog.text
        assert "source=shutdown" not in caplog.text
    finally:
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)
