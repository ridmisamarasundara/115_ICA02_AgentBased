import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"  # before app code is imported
os.environ["APP_ENV"] = "test"                      # keeps the background timer off during tests

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base


@pytest.fixture
def db():
    """Fresh in-memory database for every test."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
