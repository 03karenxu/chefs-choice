import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from decimal import Decimal

from app.enums import PriceLevel
from app.main import app
from app.db import Base, get_db
from app.models import Restaurant


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def seeded_db(db_session: Session):

    restaurants = [
        Restaurant(
            id="rest-001",
            name="The Golden Spoon",
            type="Italian",
            address="123 Main St, Springfield",
            lat=39.7817,
            lng=-89.6501,
            priceLevel=PriceLevel.MODERATE,
            priceRange="CAD 20-30",
            rating=Decimal("4.5"),
            userRatingCount=230,
        ),
        Restaurant(
            id="rest-002",
            name="Sushi Circle",
            type="Japanese",
            address="456 Oak Ave, Springfield",
            lat=39.7901,
            lng=-89.6440,
            priceLevel=PriceLevel.EXPENSIVE,
            priceRange="CAD 20-80",
            rating=Decimal("4.8"),
            userRatingCount=512,
        ),
        Restaurant(
            id="rest-003",
            name="Chronic Tacos",
            type="Mexican",
            address="789 Elm St, Springfield",
            lat=39.7750,
            lng=-89.6600,
            priceLevel=PriceLevel.INEXPENSIVE,
            priceRange="CAD 10-20",
            rating=Decimal("3.9"),
            userRatingCount=88,
        ),
        Restaurant(
            id="rest-004",
            name="Taco Fiesta",
            type="Mexican",
            address="321 Pine Rd, Springfield",
            lat=39.7690,
            lng=-89.6550,
            priceLevel=PriceLevel.INEXPENSIVE,
            priceRange="CAD 10-20",
            rating=Decimal("4.2"),
            userRatingCount=310,
        ),
        Restaurant(
            id="rest-005",
            name="Le Petit Bistro",
            type=None,
            address="654 Maple Dr, Springfield",
            lat=39.7850,
            lng=-89.6480,
            priceLevel=None,
            priceRange=None,
            rating=None,
            userRatingCount=None,
        ),
    ]

    db_session.add_all(restaurants)
    db_session.commit()
    return restaurants