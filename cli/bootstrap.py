from api.db.models import initialize_database


def bootstrap() -> None:
    initialize_database()

