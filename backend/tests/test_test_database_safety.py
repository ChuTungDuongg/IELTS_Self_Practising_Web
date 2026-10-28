import pytest

from testsupport.test_database import validate_test_database_url


def test_test_database_requires_distinct_local_test_database():
    app = "postgresql+asyncpg://user:secret@localhost:5433/ielts"
    assert (
        validate_test_database_url(
            "postgresql+asyncpg://tester:other@127.0.0.1:55432/ielts_test", app
        ).database
        == "ielts_test"
    )
    for bad in (
        "",
        "postgresql+asyncpg://tester:other@localhost:55432/ielts",
        "postgresql+asyncpg://tester:other@example.com:55432/ielts_test",
        "postgresql+asyncpg://tester:other@localhost:5433/ielts",
    ):
        with pytest.raises(ValueError):
            validate_test_database_url(bad, app)


def test_test_database_rejects_same_database_even_with_other_credentials():
    with pytest.raises(ValueError):
        validate_test_database_url(
            "postgresql+asyncpg://other:other@127.0.0.1:5432/ielts_test",
            "postgresql+asyncpg://user:secret@localhost:5432/ielts_test",
        )
