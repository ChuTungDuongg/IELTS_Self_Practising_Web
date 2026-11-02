"""Actual application lifecycles; no SQL, identity override or synthetic response DTOs."""

from benchmarks.load.contracts import (
    answer_payload,
    attempt_payload,
    mock_payload,
    require,
    writing_payload,
)


def login(api, account):
    response = api(
        "POST",
        "/auth/login",
        "auth.login",
        json={key: account[key] for key in ("email", "password")},
    )
    require(response["user"]["id"] == account["id"], "LOGIN_IDENTITY_MISMATCH")


def save_objective(api, pause, attempt_id, *, audio=False):
    exam = api("GET", f"/attempts/{attempt_id}/exam", "attempt.exam", active=True)
    units = exam["listening_parts"] if audio else exam["passages"]
    require(bool(units), "EXAM_CONTENT_EMPTY")
    if audio:
        asset = exam.get("listening_audio_asset")
        require(bool(asset), "LISTENING_AUDIO_MISSING")
        content = api(
            "GET",
            asset["content_url"],
            "listening.audio_range",
            expected=(206,),
            headers={"Range": "bytes=0-1023"},
            binary=True,
        )
        require(0 < len(content) <= 1024, "AUDIO_RANGE_NOT_BOUNDED")
    saved_count, expected_answers = 0, {}
    for unit in units:
        api(
            "POST",
            f"/attempts/{attempt_id}/navigation",
            "attempt.navigation",
            json={"kind": "LISTENING_PART" if audio else "PASSAGE", "target_id": unit["id"]},
        )
        for group in unit["question_groups"]:
            for question in group["questions"]:
                revision = question["answer_revision"]
                # First entry and one genuine revision; do not hide 409 conflicts by retrying blindly.
                for value in ("draft", "fixture") if saved_count % 10 == 0 else ("fixture",):
                    saved = api(
                        "PUT",
                        f"/attempts/{attempt_id}/answers/{question['id']}",
                        "answer.autosave",
                        json=answer_payload(value, revision),
                    )
                    require(saved["revision"] == revision + 1, "ANSWER_REVISION_MISMATCH")
                    require(saved["value"] == value, "ANSWER_VALUE_MISMATCH")
                    require(
                        saved["is_correct"] in {True, False, None},
                        "ANSWER_RESPONSE_INVALID",
                    )
                    revision = saved["revision"]
                expected_answers[question["id"]] = "fixture"
                saved_count += 1
                pause(0.15)
    require(saved_count == 40, "OBJECTIVE_FIXTURE_QUESTION_COUNT")
    return expected_answers


def submit(api, aid):
    result = api("POST", f"/attempts/{aid}/submit", "attempt.submit")
    require(result["status"] in {"SUBMITTED", "AUTO_SUBMITTED"}, "ATTEMPT_NOT_FINALIZED")
    return result


def review(api, aid, expected_answers=None, expected_writing=None):
    result = api("GET", f"/attempts/{aid}/review", "attempt.review")
    require(
        result["attempt"]["status"] in {"SUBMITTED", "AUTO_SUBMITTED"},
        "REVIEW_BEFORE_FINALIZATION",
    )
    if expected_answers is not None:
        require(
            {answer["question_id"]: answer["value"] for answer in result["answers"]}
            == expected_answers,
            "REVIEW_ANSWER_MISMATCH",
        )
    if expected_writing is not None:
        require(
            {answer["writing_task_id"]: answer["content"] for answer in result["writing_responses"]}
            == expected_writing,
            "REVIEW_WRITING_MISMATCH",
        )


def exam_a(api, pause, fixture, cohort, iteration):
    login(api, cohort["student"])
    catalog = api("GET", "/tests?public_only=true&include_details=true", "catalog", active=True)
    require(
        any(item["id"] == fixture["test_id"] for item in catalog),
        "CATALOG_FIXTURE_MISSING",
    )
    module = "READING" if iteration % 2 == 0 else "LISTENING"
    started = api(
        "POST",
        "/attempts",
        "attempt.start",
        expected=(201,),
        json=attempt_payload(fixture["version_id"], module),
    )
    expected_answers = save_objective(
        api, pause, started["attempt_id"], audio=module == "LISTENING"
    )
    pause(1)
    submit(api, started["attempt_id"])
    review(api, started["attempt_id"], expected_answers)
    api("GET", "/history", "history")


def speaking_lifecycle(api, pause, aid):
    state = api("GET", f"/speaking-attempts/{aid}/state", "speaking.state", active=True)
    prompts = 0
    while state["phase"] != "COMPLETED":
        require(
            prompts < 3 and state["current_prompt"] is not None,
            "SPEAKING_PROGRESS_INVALID",
        )
        prompt = state["current_prompt"]
        state = api(
            "POST",
            f"/speaking-attempts/{aid}/begin",
            "speaking.begin",
            json={"prompt_id": prompt["id"]},
            active=True,
        )
        # Server owns PREPARING/STARTING/RECORDING deadlines. Poll boundedly, never edit DB clocks.
        for _ in range(30):
            if state["phase"] in {"RECORDING", "FINALIZING"}:
                break
            pause(0.3)
            state = api("GET", f"/speaking-attempts/{aid}/state", "speaking.state", active=True)
        require(state["phase"] in {"RECORDING", "FINALIZING"}, "SPEAKING_RECORDING_TIMEOUT")
        pause(0.5)
        state = api(
            "POST",
            f"/speaking-attempts/{aid}/finish",
            "speaking.finish",
            json={
                "prompt_id": prompt["id"],
                "take_number": state["take_number"],
                "completion_reason": "USER_DONE",
            },
            active=True,
        )
        prompts += 1
    require(prompts == 3, "SPEAKING_PROMPT_COUNT")


def full_mock_b(api, pause, fixture, cohort, _iteration):
    login(api, cohort["student"])
    started = api(
        "POST",
        "/test-sessions",
        "mock.start",
        expected=(201,),
        json=mock_payload(fixture["version_id"]),
    )
    sid, current = started["session"]["session_id"], started["current_attempt"]
    attempt_ids, expected_by_attempt, writing_by_attempt = [], {}, {}
    for module in ("LISTENING", "READING", "WRITING", "SPEAKING"):
        require(current["module"] == module, "MOCK_MODULE_ORDER_INVALID")
        aid = current["attempt_id"]
        attempt_ids.append(aid)
        if module in {"LISTENING", "READING"}:
            expected_by_attempt[aid] = save_objective(api, pause, aid, audio=module == "LISTENING")
            submit(api, aid)
        elif module == "WRITING":
            writing_by_attempt[aid] = {}
            exam = api("GET", f"/attempts/{aid}/exam", "attempt.exam", active=True)
            require(len(exam["writing_tasks"]) == 2, "WRITING_TASKS_MISSING")
            for task in exam["writing_tasks"]:
                revision = task["response_revision"]
                for stage in range(2):
                    content = (
                        "In the fictional town of Nerula, a garden gives residents a quiet place to meet. "
                        * (12 + stage * 10)
                    ).strip()
                    saved = api(
                        "PUT",
                        f"/attempts/{aid}/writing/{task['id']}",
                        "writing.autosave",
                        json=writing_payload(content, revision),
                    )
                    require(
                        saved["revision"] == revision + 1 and saved["word_count"] > 0,
                        "WRITING_REVISION_MISMATCH",
                    )
                    require(saved["content"] == content, "WRITING_VALUE_MISMATCH")
                    writing_by_attempt[aid][task["id"]] = content
                    revision = saved["revision"]
                    pause(0.5)
            submit(api, aid)
        else:
            # No recording media/AI in B: this exercises the supported no-audio completion acknowledgement.
            speaking_lifecycle(api, pause, aid)
        if module != "SPEAKING":
            locked = api(
                "GET",
                f"/attempts/{aid}/review",
                "mock.review_locked",
                expected=(403, 409),
            )
            require(
                locked.get("code") == "FULL_MOCK_REVIEW_LOCKED",
                "MOCK_REVIEW_LOCK_BROKEN",
            )
            current = api("POST", f"/test-sessions/{sid}/advance", "mock.advance")[
                "current_attempt"
            ]
    complete = api("GET", f"/test-sessions/{sid}", "mock.get")
    require(
        complete["status"] == "COMPLETED" and len(complete["attempts"]) == 4,
        "MOCK_NOT_COMPLETED",
    )
    for aid in attempt_ids[:3]:
        review(api, aid, expected_by_attempt.get(aid), writing_by_attempt.get(aid))
    api("GET", "/history", "history")


def classroom_c(api, pause, fixture, cohort, _iteration):
    room, assignment = cohort["classroom_id"], cohort["assignment_id"]
    login(api, cohort["student"])
    api("GET", "/classrooms", "classroom.list")
    api("GET", f"/classrooms/{room}/classwork", "classroom.classwork")
    assignments = api("GET", f"/me/classrooms/{room}/assignments", "classroom.assignments")
    require(
        any(item["id"] == assignment for item in assignments),
        "ASSIGNMENT_SCOPE_MISSING",
    )
    api("GET", "/notifications?limit=20", "notifications.list")
    api("GET", "/notifications/unread-count", "notifications.unread")
    started = api(
        "POST",
        f"/classroom-assignments/{assignment}/start",
        "assignment.start",
        expected=(201,),
        json={"mode": "MODULE", "module": "READING"},
    )
    expected_answers = save_objective(api, pause, started["attempt_id"])
    submit(api, started["attempt_id"])
    review(api, started["attempt_id"], expected_answers)
    api("GET", f"/classrooms/{room}/my-progress", "learning.student")
    api("GET", f"/classrooms/{room}/my-recommendations", "learning.recommendations")
    api("POST", "/notifications/read-all", "notifications.read", expected=(204,))
    # Login clears previous cookies, preventing teacher/student identity residue.
    login(api, cohort["teacher"])
    results = api(
        "GET",
        f"/classrooms/{room}/assignments/{assignment}/results?limit=20",
        "classroom.results",
    )
    require(bool(results), "CLASSROOM_RESULT_MISSING")
    api("GET", f"/classrooms/{room}/analytics", "learning.teacher")
    api(
        "GET",
        f"/classrooms/{room}/students/{cohort['student']['id']}/analytics",
        "learning.teacher_student",
    )


JOURNEYS = {"A": exam_a, "B": full_mock_b, "C": classroom_c}
