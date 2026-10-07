"""ORM models. Import every model module here so Alembic autogenerate sees it."""

from app.models.stock import Stock

__all__ = ["Stock"]
