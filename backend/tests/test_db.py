from sqlalchemy import create_engine, text

from app.core.config import get_settings


def test_test_database_is_reachable() -> None:
    engine = create_engine(get_settings().database_url(test=True))
    with engine.connect() as conn:
        assert conn.execute(text("select current_database()")).scalar_one() == get_settings().postgres_test_db
    engine.dispose()
