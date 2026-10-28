"""Reject database targets that are not explicitly isolated for testing."""

import re

from sqlalchemy.engine import make_url


def validate_test_database_url(test_url: str, application_url: str):
    try:
        test = make_url(test_url)
        app = make_url(application_url)
    except Exception:
        raise ValueError("TEST_DATABASE_URL must be a valid PostgreSQL test connection") from None
    hosts = {"localhost", "127.0.0.1", "::1"}
    if (
        test.drivername != "postgresql+asyncpg"
        or test.host not in hosts
        or not test.database
        or not re.search(r"(?:^|_)test(?:_|$)", test.database, re.IGNORECASE)
    ):
        raise ValueError("TEST_DATABASE_URL must name a local, dedicated test database")
    same_host = test.host == app.host or (test.host in hosts and app.host in hosts)
    if same_host and (test.port or 5432) == (app.port or 5432) and test.database == app.database:
        raise ValueError("TEST_DATABASE_URL must not point to the application database")
    return test
