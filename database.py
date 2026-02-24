import os

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "")

engine = create_engine(DATABASE_URL) if DATABASE_URL else None


def get_session():
    with Session(engine) as session:
        yield session


def create_db_and_tables():
    if engine is None:
        return
    SQLModel.metadata.create_all(engine)
