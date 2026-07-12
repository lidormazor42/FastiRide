from tests.conftest import make_user, login, make_event, make_ride


def test_create_event_requires_login(client):
    res = client.post("/api/events", json={"name": "Fest", "date": "2026-08-01", "owner_phone": "0501234567"})
    assert res.status_code == 401


def test_create_event_rejects_bad_phone(client, db):
    user = make_user(db)
    login(client, user)
    res = client.post("/api/events", json={"name": "Fest", "date": "2026-08-01", "owner_phone": "123"})
    assert res.status_code == 400


def test_create_event_success(client, db):
    user = make_user(db)
    login(client, user)
    res = client.post("/api/events", json={"name": "Fest", "date": "2026-08-01", "owner_phone": "050-123-4567"})
    assert res.status_code == 200
    body = res.json()
    assert body["owner_email"] == user.email
    assert body["owner_phone"] == "0501234567"


def test_create_event_duplicate_name_date_conflicts(client, db):
    user = make_user(db)
    login(client, user)
    payload = {"name": "Fest", "date": "2026-08-01", "owner_phone": "0501234567"}
    assert client.post("/api/events", json=payload).status_code == 200
    res = client.post("/api/events", json=payload)
    assert res.status_code == 409


def test_only_owner_can_update_event(client, db):
    owner = make_user(db, email="owner@example.com")
    other = make_user(db, email="other@example.com")
    event = make_event(db, owner_email=owner.email)

    login(client, other)
    res = client.patch(f"/api/events/{event.id}", json={"name": "Hijacked"})
    assert res.status_code == 403

    login(client, owner)
    res = client.patch(f"/api/events/{event.id}", json={"name": "Renamed"})
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed"


def test_public_events_hide_owner_contact_and_reference_tickets(client, db):
    """GET /api/events is unauthenticated — it must never expose the
    producer's phone/email or the reference-ticket images (the forgery
    baseline). It's also the page-load hot path, so keeping the base64
    blobs out is what keeps the board fast."""
    make_event(db)
    res = client.get("/api/events")
    assert res.status_code == 200
    ev = res.json()[0]
    assert "owner_phone" not in ev
    assert "owner_email" not in ev
    assert "reference_tickets" not in ev
    assert set(ev) == {"id", "name", "location", "date", "logo_url"}


def test_ownerless_event_is_locked_not_open(client, db):
    user = make_user(db)
    event = make_event(db, owner_email=None)
    login(client, user)
    res = client.patch(f"/api/events/{event.id}", json={"name": "Hijacked"})
    assert res.status_code == 403


def test_cannot_delete_event_with_active_rides(client, db):
    owner = make_user(db, email="owner@example.com")
    event = make_event(db, owner_email=owner.email)
    make_ride(db, event.id)

    login(client, owner)
    res = client.delete(f"/api/events/{event.id}")
    assert res.status_code == 400
