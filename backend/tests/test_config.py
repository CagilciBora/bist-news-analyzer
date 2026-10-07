from app.core.config import Settings


def test_database_url_switches_to_test_db() -> None:
    settings = Settings(
        _env_file=None,
        postgres_user="u",
        postgres_password="p",
        postgres_db="main",
        postgres_test_db="tst",
        postgres_host="h",
        postgres_port=1234,
    )

    assert settings.database_url() == "postgresql+psycopg://u:p@h:1234/main"
    assert settings.database_url(test=True) == "postgresql+psycopg://u:p@h:1234/tst"


def test_password_is_hidden_from_repr() -> None:
    settings = Settings(_env_file=None, postgres_password="secret")

    assert "secret" not in repr(settings)
