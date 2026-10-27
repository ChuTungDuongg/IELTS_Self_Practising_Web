import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.models import Classroom, ClassroomInvitation, ClassroomMembership, Notification, User
from app.models.enums import (
    ClassroomStatus,
    InvitationStatus,
    NotificationEntityType,
    NotificationType,
    UserRole,
)
from app.schemas.auth import RegisterRequest
from app.schemas.classrooms import ClassroomCreate, ClassroomUpdate, InvitationCreate
from app.services.auth import AuthService, GoogleIdentity
from app.services.classrooms import ClassroomService
from app.services.notifications import NotificationService
from tests.teacher_helpers import api_client, make_user


async def classroom(session, teacher):
    return await ClassroomService(session, teacher).create(ClassroomCreate(name="Fictional class"))


async def invitation(session, teacher, room_id, email):
    return await ClassroomService(session, teacher).invite(room_id, InvitationCreate(email=email))


async def count(session, model, *conditions):
    async with session.begin():
        return await session.scalar(select(func.count()).select_from(model).where(*conditions))


@pytest.mark.asyncio
async def test_classroom_ownership_archive_restore_and_historical_read(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    other = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    admin = db_session.info["current_user_identity"]
    for actor in (student, admin):
        with pytest.raises(AppError) as error:
            await classroom(db_session, actor)
        assert error.value.code == "TEACHER_REQUIRED"
    room = await classroom(db_session, teacher)
    assert room.teacher_id == teacher.id and room.status == ClassroomStatus.ACTIVE
    with pytest.raises(AppError) as error:
        await ClassroomService(db_session, other).update(room.id, ClassroomUpdate(name="Stolen"))
    assert error.value.code == "CLASSROOM_OWNERSHIP_REQUIRED"
    inv = await invitation(db_session, teacher, room.id, student.email)
    await ClassroomService(db_session, student).accept(inv.id)
    await ClassroomService(db_session, teacher).archive(room.id)
    assert (
        await ClassroomService(db_session, student).get(room.id)
    ).status == ClassroomStatus.ARCHIVED
    for operation in (
        lambda: invitation(db_session, teacher, room.id, other.email),
        lambda: ClassroomService(db_session, teacher).update(
            room.id, ClassroomUpdate(description="New")
        ),
        lambda: ClassroomService(db_session, teacher).remove_member(room.id, student.id),
        lambda: ClassroomService(db_session, student).leave(room.id),
    ):
        with pytest.raises(AppError) as error:
            await operation()
        assert error.value.code == "CLASSROOM_ARCHIVED"
    with pytest.raises(AppError) as error:
        await ClassroomService(db_session, teacher).restore(room.id)
    assert error.value.code == "ADMIN_REQUIRED"
    assert (
        await ClassroomService(db_session, admin).restore(room.id)
    ).status == ClassroomStatus.ACTIVE
    await ClassroomService(db_session, admin).archive(room.id)


@pytest.mark.asyncio
async def test_existing_unknown_invites_duplicates_recipient_auth_and_notifications(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    wrong = await make_user(db_session)
    room = await classroom(db_session, teacher)
    inv = await invitation(db_session, teacher, room.id, f"  {student.email.upper()}  ")
    assert inv.invited_user_id == student.id and inv.classroom_name == room.name
    assert (await NotificationService(db_session, student).unread_count()).unread_count == 1
    with pytest.raises(AppError) as error:
        await invitation(db_session, teacher, room.id, student.email)
    assert error.value.code == "INVITATION_ALREADY_PENDING"
    with pytest.raises(AppError) as error:
        await invitation(db_session, teacher, room.id, teacher.email)
    assert error.value.code == "CLASSROOM_OWNER_INVITATION"
    with pytest.raises(AppError) as error:
        await ClassroomService(db_session, wrong).accept(inv.id)
    assert error.value.code == "INVITATION_EMAIL_MISMATCH"
    unknown = await invitation(db_session, teacher, room.id, f"unknown-{uuid4()}@example.com")
    assert unknown.invited_user_id is None
    member = await ClassroomService(db_session, student).accept(inv.id)
    assert member.user_id == student.id
    with pytest.raises(AppError) as error:
        await ClassroomService(db_session, student).accept(inv.id)
    assert error.value.code == "INVITATION_ALREADY_RESOLVED"
    with pytest.raises(AppError) as error:
        await invitation(db_session, teacher, room.id, student.email)
    assert error.value.code == "ACTIVE_MEMBERSHIP_EXISTS"
    assert (
        await count(db_session, ClassroomMembership, ClassroomMembership.classroom_id == room.id)
        == 1
    )
    assert (await NotificationService(db_session, teacher).unread_count()).unread_count == 1


@pytest.mark.asyncio
async def test_decline_cancel_leave_remove_and_rejoin_preserve_membership_periods(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    room = await classroom(db_session, teacher)
    inv = await invitation(db_session, teacher, room.id, student.email)
    assert (
        await ClassroomService(db_session, student).decline(inv.id)
    ).status == InvitationStatus.DECLINED
    assert (
        await count(db_session, ClassroomMembership, ClassroomMembership.classroom_id == room.id)
        == 0
    )
    inv2 = await invitation(db_session, teacher, room.id, student.email)
    assert (
        await ClassroomService(db_session, teacher).cancel(inv2.id)
    ).status == InvitationStatus.CANCELLED
    inv3 = await invitation(db_session, teacher, room.id, student.email)
    first = await ClassroomService(db_session, student).accept(inv3.id)
    await ClassroomService(db_session, student).leave(room.id)
    inv4 = await invitation(db_session, teacher, room.id, student.email)
    second = await ClassroomService(db_session, student).accept(inv4.id)
    assert first.id != second.id
    await ClassroomService(db_session, teacher).remove_member(room.id, student.id)
    members = (await ClassroomService(db_session, teacher).members(room.id)).items
    assert len(members) == 2 and all(member.left_at for member in members)
    assert {member.removed_by_user_id for member in members} == {None, teacher.id}
    assert all(member.email == student.email and member.display_name for member in members)
    assert (await ClassroomService(db_session, student).get(room.id)).id == room.id


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_mode", ["register", "password", "google"])
async def test_future_auth_binds_pending_email_once_without_auto_join(db_session, auth_mode):
    teacher = await make_user(db_session, UserRole.TEACHER)
    room = await classroom(db_session, teacher)
    email = f"future-{uuid4()}@example.com"
    inv = await invitation(db_session, teacher, room.id, email)
    auth = AuthService(db_session, get_settings())
    if auth_mode == "register":
        user = await auth.register(
            RegisterRequest(email=email, display_name="New learner", password="StrongPassword123!")
        )
    elif auth_mode == "password":
        async with db_session.begin():
            user = User(
                email=email,
                display_name="Learner",
                role=UserRole.USER,
                is_active=True,
                password_hash=hash_password("StrongPassword123!"),
            )
            db_session.add(user)
        user = await auth.authenticate(email.upper(), "StrongPassword123!")
    else:
        identity = GoogleIdentity(
            subject=str(uuid4()), email=email, display_name="Learner", email_verified=True
        )
        user = await auth.find_or_link_google(identity)
        await auth.find_or_link_google(identity)
    if auth_mode == "google":
        await auth.find_or_link_google(identity)
    else:
        await auth.authenticate(email, "StrongPassword123!")
    mine = (await ClassroomService(db_session, user).my_invitations()).items
    assert len(mine) == 1 and mine[0].id == inv.id and mine[0].invited_user_id == user.id
    assert mine[0].status == InvitationStatus.PENDING
    assert (
        await count(db_session, ClassroomMembership, ClassroomMembership.classroom_id == room.id)
        == 0
    )
    assert await count(db_session, Notification, Notification.user_id == user.id) == 1


@pytest.mark.asyncio
async def test_notification_reads_recipient_scoping_idempotency_and_no_authority(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    wrong = await make_user(db_session)
    room = await classroom(db_session, teacher)
    inv = await invitation(db_session, teacher, room.id, student.email)
    notifications = NotificationService(db_session, student)
    listed = await notifications.list()
    assert len(listed.items) == 1 and listed.items[0].read_at is None
    assert (await notifications.unread_count()).unread_count == 1
    with pytest.raises(AppError) as error:
        await NotificationService(db_session, wrong).mark_read(listed.items[0].id)
    assert error.value.status_code == 404
    async with db_session.begin():
        await NotificationService(db_session, wrong).create_once(
            user_id=wrong.id,
            type=NotificationType.CLASSROOM_INVITED,
            entity_type=NotificationEntityType.INVITATION,
            entity_id=inv.id,
            payload={"classroom_name": room.name},
        )
        await NotificationService(db_session, wrong).create_once(
            user_id=wrong.id,
            type=NotificationType.CLASSROOM_INVITED,
            entity_type=NotificationEntityType.INVITATION,
            entity_id=inv.id,
            payload={"classroom_name": room.name},
        )
    assert await count(db_session, Notification, Notification.user_id == wrong.id) == 1
    with pytest.raises(AppError):
        await ClassroomService(db_session, wrong).accept(inv.id)
    first = await notifications.mark_read(listed.items[0].id)
    again = await notifications.mark_read(listed.items[0].id)
    assert first.read_at is not None and first.read_at == again.read_at
    await invitation(db_session, teacher, (await classroom(db_session, teacher)).id, student.email)
    assert (await notifications.unread_count()).unread_count == 1
    await notifications.mark_all_read()
    assert (await notifications.unread_count()).unread_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["accept", "decline", "cancel"])
async def test_archived_invitation_actions_cannot_change_membership(db_session, action):
    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    room = await classroom(db_session, teacher)
    inv = await invitation(db_session, teacher, room.id, student.email)
    await ClassroomService(db_session, teacher).archive(room.id)
    actor = teacher if action == "cancel" else student
    with pytest.raises(AppError) as error:
        await getattr(ClassroomService(db_session, actor), action)(inv.id)
    assert error.value.code == "CLASSROOM_ARCHIVED"
    assert (
        await count(db_session, ClassroomMembership, ClassroomMembership.classroom_id == room.id)
        == 0
    )
    assert (await ClassroomService(db_session, student).my_invitations()).items[
        0
    ].status == InvitationStatus.PENDING


@pytest.mark.asyncio
async def test_other_teacher_cannot_manage_members_invites_or_known_classroom_ids(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    other = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    room = await classroom(db_session, teacher)
    inv = await invitation(db_session, teacher, room.id, student.email)
    other_service = ClassroomService(db_session, other)
    for operation, expected_code in (
        (lambda: other_service.members(room.id), "CLASSROOM_CAPABILITY_REQUIRED"),
        (lambda: other_service.invitations(room.id), "CLASSROOM_CAPABILITY_REQUIRED"),
        (
            lambda: other_service.invite(room.id, InvitationCreate(email=other.email)),
            "CLASSROOM_CAPABILITY_REQUIRED",
        ),
        (lambda: other_service.cancel(inv.id), "CLASSROOM_CAPABILITY_REQUIRED"),
        (lambda: other_service.archive(room.id), "CLASSROOM_OWNERSHIP_REQUIRED"),
        (
            lambda: other_service.remove_member(room.id, student.id),
            "CLASSROOM_CAPABILITY_REQUIRED",
        ),
    ):
        with pytest.raises(AppError) as error:
            await operation()
        assert (error.value.code, error.value.status_code) == (expected_code, 403)
    assert (await other_service.list()).items == []
    with pytest.raises(AppError) as error:
        await other_service.get(room.id)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_notification_event_rolls_back_with_caller_domain_transaction(db_session):
    student = await make_user(db_session)
    notifications = NotificationService(db_session, student)
    with pytest.raises(RuntimeError, match="Domain operation failed"):
        async with db_session.begin():
            await notifications.create_once(
                user_id=student.id,
                type=NotificationType.CLASSROOM_ARCHIVED,
                entity_type=NotificationEntityType.CLASSROOM,
                entity_id=uuid4(),
                payload={},
            )
            raise RuntimeError("Domain operation failed")
    assert (await notifications.unread_count()).unread_count == 0


@pytest.mark.asyncio
async def test_classroom_restore_rejects_demoted_owner_without_erasing_history(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    room = await classroom(db_session, teacher)
    await ClassroomService(db_session, teacher).archive(room.id)
    async with db_session.begin():
        stored_teacher = await db_session.get(User, teacher.id)
        stored_teacher.role = UserRole.USER
    with pytest.raises(AppError) as error:
        await ClassroomService(db_session, db_session.info["current_user_identity"]).restore(
            room.id
        )
    assert error.value.code == "TEACHER_REQUIRED"
    assert await count(db_session, Classroom, Classroom.id == room.id) == 1


@pytest.mark.asyncio
async def test_api_contract_notifications_and_classroom_actions(db_session):
    teacher = await make_user(db_session, UserRole.TEACHER)
    student = await make_user(db_session)
    async with api_client(db_session, teacher) as client:
        response = await client.post("/api/v1/classrooms", json={"name": "Contract room"})
        assert response.status_code == 201
        room_id = response.json()["id"]
        inv = await client.post(
            f"/api/v1/classrooms/{room_id}/invitations", json={"email": student.email}
        )
        assert inv.status_code == 201
        inv_id = inv.json()["id"]
    async with api_client(db_session, student) as client:
        assert (
            await client.post("/api/v1/classrooms", json={"name": "Not allowed"})
        ).status_code == 403
        assert (await client.get("/api/v1/me/classroom-invitations")).json()["items"][0][
            "id"
        ] == inv_id
        assert (await client.get("/api/v1/notifications/unread-count")).json()["unread_count"] == 1
        listed = (await client.get("/api/v1/notifications")).json()
        assert listed["items"][0]["read_at"] is None
        assert (
            await client.post(f"/api/v1/classroom-invitations/{inv_id}/accept")
        ).status_code == 200
        assert (await client.get(f"/api/v1/classrooms/{room_id}")).status_code == 200
        assert (await client.post("/api/v1/notifications/read-all")).status_code == 204


@pytest.mark.asyncio
async def test_concurrent_accept_creates_exactly_one_membership():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    teacher_id = student_id = room_id = invitation_id = None
    try:
        async with factory() as session:
            teacher = await make_user(session, UserRole.TEACHER)
            student = await make_user(session)
            teacher_id, student_id = teacher.id, student.id
            room = await classroom(session, teacher)
            inv = await invitation(session, teacher, room.id, student.email)
            room_id, invitation_id = room.id, inv.id

        async def accept_once():
            async with factory() as session:
                async with session.begin():
                    actor = await session.get(User, student_id)
                try:
                    return await ClassroomService(session, actor).accept(invitation_id)
                except AppError as error:
                    return error.code

        outcomes = await asyncio.gather(accept_once(), accept_once())
        assert sum(outcome == "INVITATION_ALREADY_RESOLVED" for outcome in outcomes) == 1
        async with factory() as session:
            assert (
                await count(
                    session, ClassroomMembership, ClassroomMembership.classroom_id == room_id
                )
                == 1
            )
            assert (
                await count(
                    session,
                    Notification,
                    Notification.user_id == teacher_id,
                    Notification.type == NotificationType.CLASSROOM_INVITATION_ACCEPTED,
                )
                == 1
            )
    finally:
        from sqlalchemy import delete

        async with factory() as session, session.begin():
            if teacher_id:
                await session.execute(
                    delete(Notification).where(Notification.user_id.in_([teacher_id, student_id]))
                )
                await session.execute(
                    delete(ClassroomMembership).where(ClassroomMembership.classroom_id == room_id)
                )
                await session.execute(
                    delete(ClassroomInvitation).where(ClassroomInvitation.classroom_id == room_id)
                )
                await session.execute(delete(Classroom).where(Classroom.id == room_id))
                await session.execute(delete(User).where(User.id.in_([teacher_id, student_id])))
        await engine.dispose()
