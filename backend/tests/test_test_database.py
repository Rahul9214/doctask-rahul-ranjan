import pytest

from app.test_database import UnsafeTestDatabaseError, assert_destructive_test_database

APPLICATION_URL = (
    "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance"
)
TEST_URL = "postgresql+asyncpg://project_assurance:local_only@localhost:5432/project_assurance_test"


def test_application_database_is_denied_even_with_opt_in() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="requires database"):
        assert_destructive_test_database(
            test_database_url=APPLICATION_URL,
            application_database_url=APPLICATION_URL,
            allow_destructive="true",
        )


def test_dedicated_test_database_is_allowed_with_opt_in() -> None:
    assert_destructive_test_database(
        test_database_url=TEST_URL,
        application_database_url=APPLICATION_URL,
        allow_destructive="TRUE",
    )


def test_missing_destructive_opt_in_is_denied() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="ALLOW_DESTRUCTIVE_TEST_DATABASE"):
        assert_destructive_test_database(
            test_database_url=TEST_URL,
            application_database_url=APPLICATION_URL,
            allow_destructive=None,
        )


def test_test_url_must_differ_from_application_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="must not identify"):
        assert_destructive_test_database(
            test_database_url=TEST_URL,
            application_database_url=TEST_URL,
            allow_destructive="true",
        )
