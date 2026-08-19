from sqlalchemy.engine import make_url

TEST_DATABASE_NAME = "project_assurance_test"


class UnsafeTestDatabaseError(RuntimeError):
    pass


def assert_destructive_test_database(
    *,
    test_database_url: str,
    application_database_url: str,
    allow_destructive: str | None,
) -> None:
    """Fail before destructive test setup unless two explicit safeguards pass."""

    if (allow_destructive or "").casefold() != "true":
        raise UnsafeTestDatabaseError(
            "Destructive integration setup requires ALLOW_DESTRUCTIVE_TEST_DATABASE=true."
        )

    test_url = make_url(test_database_url)
    application_url = make_url(application_database_url)
    if test_url.database != TEST_DATABASE_NAME:
        raise UnsafeTestDatabaseError(
            f"Destructive integration setup requires database {TEST_DATABASE_NAME!r}."
        )
    if application_url.database == test_url.database:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL must not identify the application database."
        )
