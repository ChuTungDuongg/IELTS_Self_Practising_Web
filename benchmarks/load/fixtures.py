"""Fictional deterministic shape, created exclusively through real authenticated APIs."""

import io
import secrets
import wave
from uuid import NAMESPACE_URL, uuid5

from benchmarks.load.client import GuardedClient
from benchmarks.load.safety import validate_attestation


def fictional_group(first: int, count: int) -> dict:
    return {
        "question_type": "short_answer",
        "instruction": "Write one fictional word.",
        "config": {},
        "order_index": 0,
        "questions": [
            {
                "number": first + index,
                "prompt": f"Fictional record {first + index}: name its category.",
                "config": {"max_words": 2, "max_numbers": 0},
                "answer_key": {"kind": "TEXT", "accepted": ["fixture"]},
                "order_index": index,
            }
            for index in range(count)
        ],
    }


def fictional_audio() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000 * 4)
    return stream.getvalue()


async def seed(manifest: dict, private: dict, *, students: int) -> dict:
    """One teacher/cohort per VU; never share login state or student attempt ownership."""
    run_id = manifest["run_id"]
    async with GuardedClient(manifest, private["token"]) as admin:
        identity = await admin.request("GET", "/__load__/identity", name="identity")
        validate_attestation(manifest, identity)
        await admin.request("POST", "/api/v1/auth/login", name="admin_login", json=private["admin"])
        test = await admin.request(
            "POST",
            "/api/v1/tests",
            name="create_test",
            expected=(201,),
            json={"title": f"Fictional load laboratory {run_id}"},
        )
        version = test["versions"][0]["id"]
        modules = {}
        for kind in ("LISTENING", "READING", "WRITING", "SPEAKING"):
            modules[kind] = await admin.request(
                "POST",
                f"/api/v1/test-versions/{version}/modules",
                name="create_module",
                expected=(201,),
                json={"module_type": kind, "recommended_duration_seconds": 3600},
            )
        first = 1
        for index, count in enumerate((13, 13, 14)):
            passage = await admin.request(
                "POST",
                f"/api/v1/test-versions/{version}/reading/passages",
                name="create_passage",
                expected=(201,),
                json={
                    "title": f"Fictional archive {index + 1}",
                    "order_index": index,
                    "blocks": [
                        {
                            "id": str(uuid5(NAMESPACE_URL, f"load:{run_id}:{index}")),
                            "text": "The invented town of Nerula catalogs imaginary blue stones. "
                            * 35,
                        }
                    ],
                },
            )
            await admin.request(
                "POST",
                f"/api/v1/reading/passages/{passage['id']}/question-groups",
                name="create_reading_group",
                expected=(201,),
                json=fictional_group(first, count),
            )
            first += count
        for index in range(4):
            part = await admin.request(
                "POST",
                f"/api/v1/test-versions/{version}/listening/parts",
                name="create_listening_part",
                expected=(201,),
                json={
                    "title": f"Fictional section {index + 1}",
                    "order_index": index,
                    "audio_start_seconds": index,
                    "audio_end_seconds": index + 1,
                },
            )
            await admin.request(
                "POST",
                f"/api/v1/listening/parts/{part['id']}/question-groups",
                name="create_listening_group",
                expected=(201,),
                json=dict(fictional_group(index * 10 + 1, 10), order_index=index),
            )
        audio = await admin.request(
            "POST",
            "/api/v1/assets/audio",
            name="upload_silent_audio",
            expected=(201,),
            data={"test_version_id": version},
            files={"file": ("fictional-silence.wav", fictional_audio(), "audio/wav")},
        )
        await admin.request(
            "PUT",
            f"/api/v1/listening/modules/{modules['LISTENING']['id']}/audio",
            name="attach_audio",
            json={
                "expected_revision": modules["LISTENING"]["revision"],
                "asset_id": audio["id"],
            },
        )
        for task in modules["WRITING"]["writing_tasks"]:
            await admin.request(
                "PUT",
                f"/api/v1/writing/tasks/{task['id']}",
                name="write_task",
                json={
                    "expected_revision": task["revision"],
                    "prompt": "Describe the fictional town garden."
                    if task["task_number"] == 1
                    else "Should the fictional town of Nerula create a garden? Give your opinion.",
                    "task_type": "MAP_PLAN" if task["task_number"] == 1 else "OPINION",
                    "minimum_recommended_words": task["minimum_recommended_words"],
                    "recommended_duration_seconds": task["recommended_duration_seconds"],
                },
            )
        for part in modules["SPEAKING"]["speaking_parts"]:
            await admin.request(
                "PUT",
                f"/api/v1/speaking/parts/{part['id']}",
                name="write_speaking_part",
                json={
                    "expected_revision": part["revision"],
                    "prompts": [
                        {
                            "order_index": 0,
                            "prompt_type": "LONG_TURN"
                            if part["part_number"] == 2
                            else "SHORT_ANSWER",
                            "prompt_text": f"Describe fictional town garden {part['part_number']}.",
                            "preparation_seconds": 1 if part["part_number"] == 2 else 0,
                            "response_seconds": 5,
                            "config_json": {"cue_points": ["Invent one detail"]}
                            if part["part_number"] == 2
                            else {},
                        }
                    ],
                },
            )
        await admin.request("POST", f"/api/v1/test-versions/{version}/publish", name="publish")
        accounts = []
        for index in range(students):
            pair = {}
            for role in ("teacher", "student"):
                credentials = {
                    "email": f"load-{run_id}-{role}-{index}@example.com",
                    "password": secrets.token_urlsafe(24),
                }
                async with GuardedClient(manifest, private["token"]) as user:
                    registered = await user.request(
                        "POST",
                        "/api/v1/auth/register",
                        name="register",
                        expected=(201,),
                        json=dict(credentials, display_name=f"Fictional {role} {index}"),
                    )
                    pair[role] = dict(credentials, id=registered["user"]["id"])
            await admin.request(
                "PATCH",
                f"/api/v1/admin/users/{pair['teacher']['id']}",
                name="grant_teacher",
                json={"role": "TEACHER"},
            )
            async with GuardedClient(manifest, private["token"]) as teacher:
                await teacher.request(
                    "POST",
                    "/api/v1/auth/login",
                    name="teacher_login",
                    json={k: pair["teacher"][k] for k in ("email", "password")},
                )
                room = await teacher.request(
                    "POST",
                    "/api/v1/classrooms",
                    name="create_classroom",
                    expected=(201,),
                    json={"name": f"Fictional cohort {index}"},
                )
                invite = await teacher.request(
                    "POST",
                    f"/api/v1/classrooms/{room['id']}/invitations",
                    name="invite",
                    expected=(201,),
                    json={"email": pair["student"]["email"]},
                )
                assignment = await teacher.request(
                    "POST",
                    f"/api/v1/classrooms/{room['id']}/assignments",
                    name="assign",
                    expected=(201,),
                    json={
                        "test_version_id": version,
                        "title": "Fictional Reading exercise",
                        "target": {"mode": "MODULE", "module": "READING"},
                    },
                )
            async with GuardedClient(manifest, private["token"]) as student:
                await student.request(
                    "POST",
                    "/api/v1/auth/login",
                    name="student_login",
                    json={k: pair["student"][k] for k in ("email", "password")},
                )
                await student.request(
                    "POST",
                    f"/api/v1/classroom-invitations/{invite['id']}/accept",
                    name="accept_invite",
                )
            accounts.append(dict(pair, classroom_id=room["id"], assignment_id=assignment["id"]))
        return {
            "version_id": version,
            "test_id": test["id"],
            "audio_url": audio["content_url"],
            "accounts": accounts,
        }
