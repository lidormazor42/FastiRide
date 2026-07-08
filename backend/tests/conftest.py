import os
import uuid

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

import models
import main
from database import Base, engine, SessionLocal


@pytest.fixture(autouse=True)
def _fresh_db():
    """Every test starts from empty tables — order/isolation independent."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(main.app)


def make_user(db, name="Test User", email=None, age=25):
    user = models.User(
        google_id=uuid.uuid4().hex,
        name=name,
        email=email or f"{uuid.uuid4().hex}@example.com",
        age=age,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, user):
    """Sets the session cookie the same way google_callback does."""
    client.cookies.set("session", main._make_token(user.id))


def make_event(db, owner_email="owner@example.com", name="Psytrance Fest", date="2026-08-01"):
    event = models.Event(name=name, date=date, owner_email=owner_email, owner_phone="0501234567")
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def make_ride(db, event_id, driver_email="driver@example.com", seats_available=2):
    ride = models.Ride(
        event_id=event_id,
        driver_name="Driver Name",
        driver_email=driver_email,
        city="תל אביב",
        pickup_point="תחנת רכבת",
        departure_time="14:00",
        seats_available=seats_available,
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return ride
